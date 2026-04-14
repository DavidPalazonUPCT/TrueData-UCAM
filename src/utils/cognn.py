import torch
import numpy as np
import pandas as pd
import os
import json
import math
from torch import Tensor
from torch_geometric.typing import Adj, OptTensor
from torch_geometric.utils import softmax as pyg_softmax
from torch_scatter import scatter_add, scatter_max
from torch.nn import Module, Dropout, LayerNorm, Identity
import torch.nn.functional as F
from typing import Optional, Tuple
import torch.nn as nn

from .util import set_device

from .utils_cognn.cognn_helpers import *
from .utils_cognn.action import ActionNet
from .utils_cognn.temp import TempSoftPlus


def entropy(p):
    return -(p * torch.log(p + 1e-8)).sum(dim=1)


def calculate_adjacency_matrix(edge_index, edge_weight, num_nodes):
    """
        Constructs an adjacency matrix from the given edge index and edge weights.

        This function initializes a square adjacency matrix of size (num_nodes, num_nodes)
        filled with zeros and populates it with the weights from the edges specified by
        the edge_index tensor.

        Parameters:
        ----------
        edge_index : torch.Tensor
            A 2D tensor of shape (2, num_edges) where each column represents an edge in the
            graph. The first row contains the source nodes, and the second row contains the
            destination nodes of each edge.

        edge_weight : torch.Tensor
            A 1D tensor of shape (num_edges) representing the weights associated with each
            edge specified in edge_index. The values in this tensor will be assigned to the
            corresponding positions in the adjacency matrix.

        num_nodes : int
            The total number of nodes in the graph. This determines the size of the
            resulting adjacency matrix.

        Returns:
        --------
        adj_matrix : torch.Tensor
            A 2D tensor of shape (num_nodes, num_nodes) representing the adjacency matrix
            of the graph, where each entry (i, j) holds the weight of the edge from node i
            to node j. If no edge exists, the corresponding entry will be zero.
    """
    device = edge_index.device
    adj_matrix = torch.zeros((num_nodes, num_nodes), device=device)
    adj_matrix[edge_index[0], edge_index[1]] = edge_weight
    return adj_matrix

class CoGNN(Module):
    """
        CoGNN (Conditional Graph Neural Network) class that implements a graph neural network architecture
        with various layers and pooling mechanisms, capable of learning both environmental and action embeddings.

        Parameters:
        ----------
        gumbel_args : GumbelArgs
            Arguments related to Gumbel softmax temperature and learning configuration.

        env_args : EnvArgs
            Arguments that define the environment configuration, including network loading, normalization, and other parameters.

        action_args : ActionNetArgs
            Arguments for configuring the action network used for decision making within the graph.

        pool : Pool
            A pooling function to generate embeddings for the entire graph.

        Attributes:
        ----------
        env_net : List[Module]
            The environmental network modules used in the graph processing.

        use_encoders : bool
            A flag indicating whether to use dataset encoders.

        hidden_layer_norm : Module
            Layer normalization module for normalizing hidden layers.

        dropout : Dropout
            Dropout layer for regularization.

        act : callable
            Activation function to be used in the network.

        in_act_net : ActionNet
            Action network for input processing.

        out_act_net : ActionNet
            Action network for output processing.

        dataset_encoder : DatasetEncoders
            Dataset encoder for graph edges.

        env_bond_encoder : Module
            Encoder for environmental bonds (edges).

        act_bond_encoder : Module
            Encoder for action bonds (edges).

        pooling : callable
            Function for pooling graph representations.

        adj : Tensor
            Adjacency matrix representation of the graph after processing.

        Methods:
        -------
        forward(x: Tensor, edge_index: Adj, pestat: Tensor, edge_attr: OptTensor = None,
                batch: OptTensor = None, edge_ratio_node_mask: OptTensor = None) -> Tuple[Tensor, Tensor]
            Performs a forward pass through the network, computing embeddings and edge weights.

        save_adj() -> None
            Saves the adjacency matrix to disk at specified intervals or conditions.

        create_edge_weight(edge_index: Adj, keep_in_prob: Tensor, keep_out_prob: Tensor) -> Tensor
            Computes the edge weights based on the provided probabilities for in and out edges.
    """
    def __init__(self, gumbel_args: GumbelArgs, env_args: EnvArgs, action_args: ActionNetArgs, pool: Pool, device='cpu'):
        super(CoGNN, self).__init__()
        self.device = device
        self.env_args = env_args
        self.learn_temp = gumbel_args.learn_temp
        self.temp_model = TempSoftPlus(gumbel_args=gumbel_args, env_dim=env_args.env_dim)
        self.temp = gumbel_args.temp

        self.pair_temp = float(getattr(env_args, "pair_temp", 0.6))  # <1 endurece

        self.num_layers = env_args.num_layers
        self.env_net = env_args.load_net()
        self.env_net = nn.ModuleList(self.env_net)
        for module in self.env_net:
            module.to(self.device)
        self.use_encoders = env_args.dataset_encoders.use_encoders()

        layer_norm_cls = LayerNorm if env_args.layer_norm else Identity
        #layer_norm_cls = Identity
        self.hidden_layer_norm = layer_norm_cls(env_args.env_dim)
        self.skip = env_args.skip
        self.dropout = Dropout(p=env_args.dropout)
        self.drop_ratio = env_args.dropout
        self.act = env_args.act_type.get()
        self.in_act_net = ActionNet(action_args=action_args)
        self.out_act_net = ActionNet(action_args=action_args)

        #self.logits_layer_norm = LayerNorm(env_args.env_dim, elementwise_affine=True)
        self.logits_layer_norm = Identity()
        self.logits_layer_norm.to(self.device)

        # Encoder types
        self.dataset_encoder = env_args.dataset_encoders
        self.env_bond_encoder = self.dataset_encoder.edge_encoder(emb_dim=env_args.env_dim, model_type=env_args.model_type)
        self.act_bond_encoder = self.dataset_encoder.edge_encoder(emb_dim=action_args.hidden_dim, model_type=action_args.model_type)

        # --- Temporal Reducer (para colapsar ventana T a env_dim) ---
        # Proyección aprendida: (C*T) -> env_dim
        self.temporal_proj = nn.LazyLinear(self.env_args.env_dim)
        self.edge_scorer = nn.Bilinear(env_args.env_dim, env_args.env_dim, 1, bias=True)

        # Pooling function to generate whole-graph embeddings
        self.pooling = pool.get()

        self.lambda_pair = float(getattr(env_args, "lambda_pair", 0.1))
        self.lambda_pair_warmup_iters = int(getattr(env_args, "lambda_pair_warmup_iters", 1500))

        self.tau_edges0 = 2.0
        self.tau_edges_min = 0.1
        self.tau_edges_decay = 1e-3
        self.tau_edges = self.tau_edges0

        self.logit_noise_std = 1e-3  # ruido leve

        # Move to device
        self.temp_model.to(self.device)
        self.env_net.to(self.device)
        self.in_act_net.to(self.device)
        self.out_act_net.to(self.device)
        if self.env_bond_encoder is not None:
            self.env_bond_encoder.to(self.device)
        if self.act_bond_encoder is not None:
            self.act_bond_encoder.to(self.device)
        if isinstance(self.pooling, torch.nn.Module):
            self.pooling.to(self.device)

        # --- logging / export buffers ---
        self.entropy_in_list = []  # sólo para logging (escalares)
        self.entropy_out_list = []  # sólo para logging (escalares)
        self.entropy_in_vec = None  # vector por nodo (último forward)
        self.entropy_out_vec = None  # vector por nodo (último forward)

        self.to(self.device)

        def _init_action_head(module: nn.Module):
            # Busca la última Linear con out_features==2
            last_linear = None
            for m in module.modules():
                if isinstance(m, nn.Linear) and m.out_features == 2:
                    last_linear = m
            if last_linear is None:
                return  # no encontró cabeza (o ActionNet no usa Linear→2)

            # Inicializa pesos y bias
            nn.init.normal_(last_linear.weight, std=0.02)
            if last_linear.bias is None:
                return

            # Desplaza el logit de la clase "mantener" (índice 1)
            with torch.no_grad():
                last_linear.bias.zero_()
                last_linear.bias[1] = 1.2  # sigmoid(1.2)≈0.77 → prior a "mantener"
                last_linear.bias[0] = -0.2  # leve empuje contra "apagar"

        # Aplica a ambas redes de acción
        _init_action_head(self.in_act_net)
        _init_action_head(self.out_act_net)

    def forward(self, x: Tensor, edge_index: Adj, pestat, edge_attr: OptTensor = None, batch: OptTensor = None,
                edge_ratio_node_mask: OptTensor = None) -> Tuple[Tensor, Tensor]:
        """
            Forward pass through the CoGNN model.

            This method processes input data, computes embeddings for the nodes, generates edge weights,
            and outputs the final results, along with edge ratio statistics if required.

            Parameters:
            ----------
            x : Tensor
                The input tensor representing node features.

            edge_index : Adj
                The adjacency list indicating the connectivity between nodes.

            pestat : Tensor
                Additional environmental state features used during computation.

            edge_attr : OptTensor, optional
                Edge attributes for edge encoding (default is None).

            batch : OptTensor, optional
                Batch information for graph representation (default is None).

            edge_ratio_node_mask : OptTensor, optional
                Mask for calculating edge ratio statistics (default is None).

            Returns:
            -------
            Tuple[Tensor, Tensor]
                A tuple containing:
                    - result : Tensor
                        The final output tensor after processing through the network.
                    - edge_ratio_tensor : Tensor
                        A tensor containing edge ratio statistics across layers.
        """
        result = 0.0
        global_iter = int(os.environ.get('iter', '0'))
        self.tau_edges = max(self.tau_edges_min, self.tau_edges0 * math.exp(-self.tau_edges_decay * global_iter))
        device = self.device
        edge_index = edge_index.to(device)

        calc_stats = edge_ratio_node_mask is not None
        if calc_stats:
            edge_ratio_edge_mask = edge_ratio_node_mask[edge_index[0]] & edge_ratio_node_mask[edge_index[1]]
            edge_ratio_list = []

        # bond encode
        if edge_attr is None or self.env_bond_encoder is None:
            env_edge_embedding = None
        else:
            env_edge_embedding = self.env_bond_encoder(edge_attr)
        if edge_attr is None or self.act_bond_encoder is None:
            act_edge_embedding = None
        else:
            act_edge_embedding = self.act_bond_encoder(edge_attr)

        # node encode
        #x_0 = x[0, 0, :, :].to(self.device)
        B, C, N, T = x.shape                                # x: (B, C, N, T)
        x = x.to(self.device)
        x_b0 = x.mean(dim=0)                                # (C, N, T): Tomamos la media del batch
        x_nodes = x_b0.permute(1, 0, 2).reshape(N, C * T)   # Reorganizamos: (C, N, T) -> (N, C*T)
        x_nodes = self.temporal_proj(x_nodes)               # (N, env_dim): Proyección aprendida a env_dim

        # Cache para export posterior
        self._last_x_input = x.detach().cpu()                # entrada original
        self._last_x_used = x_nodes.detach().cpu()           # lo que realmente usas
        self._last_pestat = pestat.detach().cpu() if isinstance(pestat, torch.Tensor) else None
        self._last_edge_attr = edge_attr.detach().cpu() if isinstance(edge_attr, torch.Tensor) else None

        if isinstance(pestat, torch.Tensor):
            pestat = pestat.to(self.device)

        x = self.env_net[0](x_nodes, pestat)                     # Paso por red de entorno
        if not self.use_encoders:
            x = self.dropout(x)
            x = self.act(x)

        # Acumular estadísticas
        logits_stats = {
            "mean_in": [],
            "std_in": [],
            "min_in": [],
            "max_in": [],
            "mean_out": [],
            "std_out": [],
            "min_out": [],
            "max_out": [],
        }
        for gnn_idx in range(self.num_layers):
            x = self.hidden_layer_norm(x)
            x_logits = self.logits_layer_norm(x)
            #x_logits = x

            # action
            in_logits = self.in_act_net(x=x_logits, edge_index=edge_index, env_edge_attr=env_edge_embedding,
                                        act_edge_attr=act_edge_embedding)  # (N, 2)
            out_logits = self.out_act_net(x=x_logits, edge_index=edge_index, env_edge_attr=env_edge_embedding,
                                          act_edge_attr=act_edge_embedding)  # (N, 2)
            # Añadir un pequeño ruido a los logits en train
            if self.training and self.logit_noise_std > 0:
                in_logits = in_logits + torch.randn_like(in_logits) * self.logit_noise_std
                out_logits = out_logits + torch.randn_like(out_logits) * self.logit_noise_std

            if os.environ['TASK'] == 'train':
                # Prints Logits metrics
                with torch.no_grad():
                    logits_stats["mean_in"].append(in_logits.mean().item())
                    logits_stats["std_in"].append(in_logits.std().item())
                    logits_stats["min_in"].append(in_logits.min().item())
                    logits_stats["max_in"].append(in_logits.max().item())
                    logits_stats["mean_out"].append(out_logits.mean().item())
                    logits_stats["std_out"].append(out_logits.std().item())
                    logits_stats["min_out"].append(out_logits.min().item())
                    logits_stats["max_out"].append(out_logits.max().item())

            # --------- Modo (train vs eval/inference) y temperatura ----------
            task_str = os.environ.get("TASK", "train").lower()
            is_train = (task_str == "train")

            # Temperatura (si tienes un scheduler propio, úsalo; sino, self.tau o un valor por defecto)
            try:
                cur_iter = int(os.environ.get("iter", "0"))
            except ValueError:
                cur_iter = 0

            temp = getattr(self, "gumbel_tau", 1.0)
            if temp is None:
                temp = getattr(self, "temp", 1.0)  # default desde gumbel_args
            if hasattr(self, "tau_by_iter") and callable(self.tau_by_iter):
                temp = self.tau_by_iter(cur_iter)

            # --------- Probabilidades "soft" (para métricas/entropía/log) ----------
            in_probs_soft = torch.softmax(in_logits, dim=1)
            out_probs_soft = torch.softmax(out_logits, dim=1)

            # ===== BUDGET de conectividad global (suave, por medias) =====
            if is_train:
                r = float(getattr(self, "keep_target", 0.65))  # objetivo de mantener ~65%
                beta = float(getattr(self, "budget_coef", 0.5))  # fuerza del budget
                keep_in_mean = in_probs_soft[:, 1].mean()
                keep_out_mean = out_probs_soft[:, 1].mean()
                L_budget = beta * ((keep_in_mean - r) ** 2 + (keep_out_mean - r) ** 2)
                # Guardamos para que el trainer lo sume a la loss
                if not hasattr(self, "_aux") or not isinstance(self._aux, dict):
                    self._aux = {}
                self._aux["L_budget"] = L_budget

            # --------- One-hot para el gating duro (Gumbel con STE en train; argmax en eval) ----------
            if is_train:
                # Muestra one-hot con STE: hard=True permite gradiente hacia los logits
                in_onehot = F.gumbel_softmax(in_logits, tau=temp, hard=True)  # [N, 2]
                out_onehot = F.gumbel_softmax(out_logits, tau=temp, hard=True)  # [N, 2]
            else:
                # Decisión determinista en inferencia/eval
                in_onehot = F.one_hot(in_logits.argmax(dim=1), num_classes=2).float()
                out_onehot = F.one_hot(out_logits.argmax(dim=1), num_classes=2).float()

            # --------- Entropías (solo en train mantenemos tensores con gradiente) ----------
            def _entropy(p):
                # p: [N,2], numéricamente estable
                return -(p.clamp_min(1e-12) * (p.clamp_min(1e-12)).log()).sum(dim=1)

            if is_train:
                in_entropy = _entropy(in_probs_soft)  # [N]
                out_entropy = _entropy(out_probs_soft)  # [N]

                # Tensores con gradiente que usará el trainer para la regularización
                self.entropy_in_mean_t = in_entropy.mean()
                self.entropy_out_mean_t = out_entropy.mean()

                # Logs auxiliares (sin grad)
                self.entropy_in_vec = in_entropy.detach().cpu()
                self.entropy_out_vec = out_entropy.detach().cpu()

                # Si prefieres listas para quick debug, conserva estas dos líneas (opcionales):
                if hasattr(self, "entropy_in_list"):
                    self.entropy_in_list.append(self.entropy_in_mean_t.detach().cpu().item())
                if hasattr(self, "entropy_out_list"):
                    self.entropy_out_list.append(self.entropy_out_mean_t.detach().cpu().item())
            else:
                # En eval/inference no regularizamos por entropía
                self.entropy_in_mean_t = None
                self.entropy_out_mean_t = None
                self.entropy_in_vec = None
                self.entropy_out_vec = None

            # Guardamos las últimas "soft" para inspección/debug offline
            self.last_in_probs = in_probs_soft.detach().cpu()
            self.last_out_probs = out_probs_soft.detach().cpu()

            # --------- Estados discretos (para imprimir y coherentes con el gating) ----------
            # Convención:
            #   in_bit  = 0 apaga ENTRANTES, 1 mantiene ENTRANTES
            #   out_bit = 0 apaga SALIENTES, 1 mantiene SALIENTES
            #   state = in_bit*2 + out_bit → 0:isolate, 1:listen, 2:forecast, 3:standard
            in_bit = in_onehot.argmax(dim=1)  # [N]
            out_bit = out_onehot.argmax(dim=1)  # [N]
            states = in_bit * 2 + out_bit  # [N]
            counts = torch.bincount(states, minlength=4)
            in_gap = in_logits[:, 1] - in_logits[:, 0]
            out_gap = out_logits[:, 1] - out_logits[:, 0]
            if self.training and int(os.environ['iter']) % int(os.environ['PRINT_EVERY']) == 0:
                with torch.no_grad():
                    print(
                        f"[DEBUG] Node states: isolate={counts[0]}, listen={counts[1]}, forecast={counts[2]}, standard={counts[3]}")
                    print(f"[DEBUG][GAP] in: mean={in_gap.mean():.4f}, std={in_gap.std():.4f}, "
                          f"min={in_gap.min():.4f}, max={in_gap.max():.4f} |\n"
                          f"             out: mean={out_gap.mean():.4f}, std={out_gap.std():.4f}, "
                          f"min={out_gap.min():.4f}, max={out_gap.max():.4f}")

            #base_w = self.create_edge_weight(edge_index=edge_index,
            #                                 keep_in_prob=in_probs, keep_out_prob=out_probs)
            # --- base_w robusto: media en vez de producto ---
            #base_w = self.create_edge_weight(edge_index=edge_index,
            #                                 keep_in_prob=in_probs, keep_out_prob=out_probs)

            #pair_w = self.compute_pair_score(x_logits, edge_index)

            base_w = self.create_edge_weight(
                edge_index=edge_index,
                keep_in_prob=in_onehot,
                keep_out_prob=out_onehot)

            # Score par-a-par + warmup de mezcla, enmascarado por el gating
            pair_w = self.compute_pair_score(x_logits, edge_index)  # (E,)
            global_iter = int(os.environ.get('iter', '0'))
            lam_max = float(self.lambda_pair)
            lam = lam_max * min(1.0, global_iter / max(1, self.lambda_pair_warmup_iters))  # 0→lam_max

            # Probabilidad par-a-par con neutral 0.5 (no 1.0) como base
            pair_prob = (1.0 - lam) * 0.5 + lam * pair_w  # (E,) en (0,1)
            pair_prob = torch.clamp(pair_prob, 1e-6, 1.0 - 1e-6)

            # Logit(par)
            pair_logit = torch.log(pair_prob) - torch.log1p(-pair_prob)  # (E,)

            # Índices origen/destino para calcular el gating por arista
            src = edge_index[0]
            dst = edge_index[1]

            if is_train:
                # gating suave (probabilidad de permitir) en (0,1)
                keep_in_soft = in_probs_soft[:, 1]  # [N]
                keep_out_soft = out_probs_soft[:, 1]  # [N]
                prior = (keep_out_soft[src] * keep_in_soft[dst]).clamp(1e-6, 1.0 - 1e-6)  # [E]

                # Mezcla en probas: comb = (1-α)*pair_prob + α*prior
                alpha = float(getattr(self, "alpha_gate_prior", 0.5))  # 0.5 por defecto
                comb = (1.0 - alpha) * pair_prob + alpha * prior
                comb = torch.clamp(comb, 1e-6, 1.0 - 1e-6)

                # Logit(comb)
                pair_logit = torch.log(comb) - torch.log1p(-comb)

            # ----------------- Temperatura segura -----------------
            tau_edges = float(getattr(self, "tau_edges", 1.0))
            tau_edges = max(tau_edges, 1e-3)  # evita división por 0

            num_nodes = x.size(0)  # <- lo usamos abajo y en renormalización si eval

            if is_train:
                # TRAIN: NO máscara dura ni renormalización adicional
                edge_weight = pyg_softmax(pair_logit / tau_edges, src, num_nodes=num_nodes)
                edge_weight = torch.nan_to_num(edge_weight, nan=0.0, posinf=1.0, neginf=0.0)
            else:
                # EVAL: gating duro en logits y softmax limpio
                mask = (base_w > 0.0)
                SENT = -1e9
                pair_logit = torch.nan_to_num(pair_logit, nan=0.0, posinf=1.0, neginf=-1.0)
                pair_logit = pair_logit.masked_fill(~mask, SENT)
                edge_weight = pyg_softmax(pair_logit / tau_edges, src, num_nodes=num_nodes)
                edge_weight = torch.nan_to_num(edge_weight, nan=0.0, posinf=1.0, neginf=0.0)

            if is_train and (self.entropy_in_mean_t is not None) and (self.entropy_out_mean_t is not None):
                entropy_mean_aux_t = 0.5 * (self.entropy_in_mean_t + self.entropy_out_mean_t)
            else:
                with torch.no_grad():
                    entropy_mean_aux_t = 0.5 * (_entropy(in_probs_soft).mean() + _entropy(out_probs_soft).mean())

            if not hasattr(self, "_aux") or not isinstance(self._aux, dict):
                self._aux = {}
            self._aux["entropy_mean"] = entropy_mean_aux_t.detach()
            self._aux["edgew_mean"] = edge_weight.mean().detach()

            # if os.environ['TASK'] == 'train' and int(os.environ['iter']) % int(os.environ['PRINT_EVERY']) == 0:
                #with torch.no_grad():
                    #num_bad = (~torch.isfinite(edge_weight)).sum().item()
                    # Top-1 por nodo-ORIGEN (donde haya al menos una arista válida)
                    #top1_vals, _ = scatter_max(edge_weight, src, dim=0, dim_size=num_nodes)
                    #valid_nodes = (top1_vals > 0)
                    #nodes_gt = (top1_vals > 0.05).float().mean().item() if valid_nodes.any() else 0.0
                    #top1_mean = top1_vals[valid_nodes].mean().item() if valid_nodes.any() else 0.0
                    #print(f"[DEBUG][EDGEW-SOFTMAX] mean={edge_weight.mean().item():.4f} "
                    #      f"nodes_gt0.05={nodes_gt:.3f} top1_mean={top1_mean:.4f} bad={num_bad}")

            # --- SNAPSHOT para visualización/reporte ---
            with torch.no_grad():
                self.snapshot = {
                    "epoch": int(os.environ.get("epoch", "0")),
                    "iter": int(os.environ.get("iter", "0")),
                    "layer": gnn_idx,  # si procede
                    "edge_index": edge_index.detach().cpu(),  # [2,E]
                    "base_w": base_w.detach().cpu(),  # (E,)
                    "edge_weight": edge_weight.detach().cpu(),  # (E,)
                    "active_edge_mask": (base_w > 0).detach().cpu(),  # bool (E,)

                    "states": states.detach().cpu(),  # (N,)
                    "in_bit": in_bit.detach().cpu(),  # (N,)
                    "out_bit": out_bit.detach().cpu(),  # (N,)
                    "in_logits": in_logits.detach().cpu(),  # (N,2)
                    "out_logits": out_logits.detach().cpu(),  # (N,2)
                    "in_gap": in_gap.detach().cpu(),  # (N,)
                    "out_gap": out_gap.detach().cpu(),  # (N,)

                    "in_probs_soft": in_probs_soft.detach().cpu(),  # (N,2)
                    "out_probs_soft": out_probs_soft.detach().cpu(),  # (N,2)
                    "entropy_in_vec": self.entropy_in_vec,  # (N,)
                    "entropy_out_vec": self.entropy_out_vec,  # (N,)

                    "tau": float(temp),
                    "lam_pair": float(lam),
                    "lambda_pair_max": float(lam_max),
                    "dropout_p": float(self.dropout.p) if hasattr(self.dropout, "p") else None
                }

            self.last_edge_weight = edge_weight.detach().cpu()
            self.learned_edge_index = edge_index

            # environment
            out = self.env_net[1 + gnn_idx](x=x, edge_index=edge_index, edge_weight=edge_weight,
                                            edge_attr=env_edge_embedding)
            out = self.dropout(out)
            out = self.act(out)

            if calc_stats:
                edge_ratio = edge_weight[edge_ratio_edge_mask].sum() / edge_weight[edge_ratio_edge_mask].shape[0]
                edge_ratio_list.append(edge_ratio.item())

            if self.skip:
                x = x + out
            else:
                x = out

        if os.environ['TASK'] == 'train' and self.training:
            def summarize(values):
                return {
                    "μ": np.mean(values),
                    "σ": np.std(values),
                    "min": np.min(values),
                    "max": np.max(values),
                }
            in_summary = summarize(logits_stats["mean_in"])
            out_summary = summarize(logits_stats["mean_out"])

            if self.training and int(os.environ['iter']) % int(os.environ['PRINT_EVERY']) == 0:
                log_in = '[IN_LOGITS] mean: {:.4f}, std: {:.4f}, min: {:.4f}, max: {:.4f}'
                print(log_in.format(in_summary['μ'], in_summary['σ'], in_summary['min'], in_summary['max']), flush=True)
                log_out = '[OUT_LOGITS] mean: {:.4f}, std: {:.4f}, min: {:.4f}, max: {:.4f}'
                print(log_out.format(out_summary['μ'], out_summary['σ'], out_summary['min'], out_summary['max']), flush=True)

                th = 0.05
                print(f"[DEBUG][EDGEW] mean={edge_weight.mean().item():.4f} "
                      f"gt{th}={(edge_weight > th).float().mean().item():.3f} "
                      f"pair_mean={pair_w.mean().item():.4f} base_mean={base_w.mean().item():.4f}")

                #print(f"[DEBUG] x.shape={tuple(x.shape)}; x_nodes.shape={tuple(x_nodes.shape)}; "
                #      f"N_by_x_nodes={x_nodes.size(0)}; N_by_edge_index={int(edge_index.max().item()) + 1}")
                #print(f"[DEBUG] in_probs.shape={tuple(in_probs.shape)}; out_probs.shape={tuple(out_probs.shape)}; "
                #      f"states_total={int((in_probs.argmax(1) * 2 + out_probs.argmax(1)).numel())}")

                if os.environ["WANDB_RUN"] == "true":
                    wandb.log({
                        "in_logits_mean": in_summary['μ'],
                        "in_logits_std": in_summary['σ'],
                        "in_logits_min": in_summary['min'],
                        "in_logits_max": in_summary['max'],
                        "out_logits_mean": out_summary['μ'],
                        "out_logits_std": out_summary['σ'],
                        "out_logits_min": out_summary['min'],
                        "out_logits_max": out_summary['max'],
                    })

        # ADJ
        self.adj = calculate_adjacency_matrix(edge_index=edge_index.to(self.device), edge_weight=edge_weight.to(self.device), num_nodes=x.shape[0])

        x = self.hidden_layer_norm(x)
        batch = torch.zeros(x.size(0), dtype=torch.long, device=self.device)
        x = self.pooling(x, batch=batch)
        x = self.env_net[-1](x)  # decoder
        result = result + x
        #result = result.to(device)

        if calc_stats:
            edge_ratio_tensor = torch.tensor(edge_ratio_list, device=x.device)
        else:
            edge_ratio_tensor = -1 * torch.ones(size=(self.num_layers,), device=x.device)
        return result, edge_ratio_tensor

    def save_adj(self):
        """
            Saves the adjacency matrix to a specified location at defined intervals or under certain conditions.

            This method checks the iteration count and saves the adjacency matrix to disk
            in both .npy and .json formats based on the environment settings.
            The saving occurs every 100 iterations or when a specific condition is met.
        """
        if "model_best" in os.environ:
            adj_np = self.adj.cpu().detach().numpy()
            devices = pd.read_csv(f"/app/data/{os.environ['CLIENT']}/DeviceImport.csv")
            devicelist = devices['name']
            df_adj = pd.DataFrame(adj_np, columns=devicelist)
            df_adj.index = devicelist
            # Save filtered edge_index if exists
            if hasattr(self, 'learned_edge_index'):
                edge_index_np = self.learned_edge_index.cpu().detach().numpy()
            else:
                edge_index_np = None
            # Save and send adj to ETL
            if os.environ['TASK'] == 're-train':
                os.makedirs(os.path.dirname(f"{os.environ['MODEL_FOLDER_PATH']}_{os.environ['DATE_YMD_HMS']}"), exist_ok=True)
                np.save(f"{os.environ['MODEL_FOLDER_PATH']}_{os.environ['DATE_YMD_HMS']}/ADP_0.npy", adj_np)
                df_adj.to_json(f"{os.environ['MODEL_FOLDER_PATH']}_{os.environ['DATE_YMD_HMS']}/adj.json",orient='index', indent=4)
                if edge_index_np is not None:
                    np.save(f"{os.environ['MODEL_FOLDER_PATH']}_{os.environ['DATE_YMD_HMS']}/learned_edge_index.npy", edge_index_np)
                # Export nodes.csv, edges.csv, mapping.json y states_legend.json
                self.save_graph_and_inputs(
                    x_input=getattr(self, "_last_x_input", None),
                    x_used=getattr(self, "_last_x_used", None),
                    pestat=getattr(self, "_last_pestat", None),
                    edge_attr=getattr(self, "_last_edge_attr", None),
                    export_dir=f"{os.environ['MODEL_FOLDER_PATH']}_{os.environ['DATE_YMD_HMS']}",
                    edge_weight_threshold=float(os.environ.get("EDGE_W_THRESH", "0")) if os.environ.get(
                        "EDGE_W_THRESH") else None
                )
                snap_dir = os.path.join(f"{os.environ['MODEL_FOLDER_PATH']}_{os.environ['DATE_YMD_HMS']}", "snapshot")
                os.makedirs(snap_dir, exist_ok=True)
                it = os.environ.get("BEST_MODEL_ITER", "0")
                snap_file = os.path.join(snap_dir, f"epoch{os.environ['epoch']}_iter{it}.pt")
                torch.save(self.snapshot, snap_file)

            else:
                np.save(f"{os.environ['SAVE_FOLDER_PATH']}/ADP_0.npy", adj_np)
                df_adj.to_json(f"{os.environ['SAVE_FOLDER_PATH']}/adj.json",orient='index', indent=4)
                if edge_index_np is not None:
                    np.save(f"{os.environ['SAVE_FOLDER_PATH']}/learned_edge_index.npy", edge_index_np)
                # Export nodes.csv, edges.csv, mapping.json y states_legend.json
                self.save_graph_and_inputs(
                    x_input=getattr(self, "_last_x_input", None),
                    x_used=getattr(self, "_last_x_used", None),
                    pestat=getattr(self, "_last_pestat", None),
                    edge_attr=getattr(self, "_last_edge_attr", None),
                    export_dir=f"{os.environ['SAVE_FOLDER_PATH']}",
                    edge_weight_threshold=float(os.environ.get("EDGE_W_THRESH", "0")) if os.environ.get(
                        "EDGE_W_THRESH") else None
                )
                snap_dir = os.path.join(os.environ['SAVE_FOLDER_PATH'], "snapshot")
                os.makedirs(snap_dir, exist_ok=True)
                it = os.environ.get("BEST_MODEL_ITER", "0")
                snap_file = os.path.join(snap_dir, f"epoch{os.environ['epoch']}_iter{it}.pt")
                torch.save(self.snapshot, snap_file)

            print("ADJ saved")

        else:
            pass

    def create_edge_weight(self, edge_index: Adj, keep_in_prob: Tensor, keep_out_prob: Tensor) -> Tensor:
        """
            Computes edge weights based on input and output probabilities for edges.

            This method multiplies the incoming and outgoing probabilities to create a combined edge weight.

            Parameters:
            ----------
            edge_index : Adj
                The adjacency list indicating the connectivity between nodes.

            keep_in_prob : Tensor
                The probabilities for incoming edges.

            keep_out_prob : Tensor
                The probabilities for outgoing edges.

            Returns:
            -------
            Tensor
                A tensor representing the computed edge weights.
        """
        u, v = edge_index
        keep_in = keep_in_prob[:, 1].to(self.device)
        keep_out = keep_out_prob[:, 1].to(self.device)
        w = keep_out[u] * keep_in[v]
        #w = 0.5 * (keep_in[v] + keep_out[u])  # media, no producto
        return w


    def _to_numpy(self, obj):
        """Convierte tensores o arrays a numpy de forma segura."""
        if obj is None:
            return None
        if isinstance(obj, torch.Tensor):
            return obj.detach().cpu().numpy()
        if isinstance(obj, np.ndarray):
            return obj
        # listas o tuplas de tensores/arrays
        if isinstance(obj, (list, tuple)):
            return [self._to_numpy(x) for x in obj]
        return obj

    def export_input_snapshot(self, x_input, x_used, pestat, edge_attr, export_dir: str):
        """
        Guarda la ventana de entrada y metadatos de ejecución.
        - x_input: tensor original pasado a forward (shape tal cual lo recibes).
        - x_used:  tensor realmente usado por la red (tu x[0,0,:,:]).
        - pestat:  tensor de estado ambiental (opcional).
        - edge_attr: atributos de arista (opcional).
        """
        os.makedirs(export_dir, exist_ok=True)

        # --- Inputs
        x_full_np = self._to_numpy(x_input)
        x_used_np = self._to_numpy(x_used)
        if x_full_np is not None:
            np.save(os.path.join(export_dir, "x_full.npy"), x_full_np)
        if x_used_np is not None:
            np.save(os.path.join(export_dir, "x_used.npy"), x_used_np)

        if isinstance(pestat, torch.Tensor):
            np.save(os.path.join(export_dir, "pestat.npy"), self._to_numpy(pestat))

        if edge_attr is not None:
            np.save(os.path.join(export_dir, "edge_attr.npy"), self._to_numpy(edge_attr))

        # --- Metadatos de ejecución (run)
        graph_meta_raw = {
            "client": os.environ.get("CLIENT", ""),
            "task": os.environ.get("TASK", ""),
            "iter": (
                int(os.environ.get("iter", "-1")) if str(os.environ.get("iter", "-1")).isdigit() else os.environ.get(
                    "iter", "-1")),
            "date_ymd_hms": os.environ.get("DATE_YMD_HMS", ""),
            "window_start": os.environ.get("WINDOW_START", ""),
            "window_end": os.environ.get("WINDOW_END", ""),
            "wandb_run": os.environ.get("WANDB_RUN", ""),
        }
        graph_meta = {k: self._json_friendly(v) for k, v in graph_meta_raw.items()}
        with open(os.path.join(export_dir, "graph_metadata.json"), "w") as f:
            json.dump(graph_meta, f, indent=2)


    def save_graph_and_inputs(self, x_input, x_used, pestat, edge_attr, export_dir: str,
                              edge_weight_threshold: float = None):
        """
        Guarda:
          - Grafo (nodes.csv, edges.csv, adj.npy, mapping.json, states_legend.json, edge_index.npy, edge_weight.npy)
          - Inputs (x_full.npy, x_used.npy, pestat.npy, edge_attr.npy)
          - Metadatos (run_metadata.json, model_metadata.json)
        edge_weight_threshold: si se indica, filtra edges con weight < umbral al escribir edges.csv
        """
        os.makedirs(export_dir, exist_ok=True)

        # --- 1) Grafo (usa tu exportación existente y añade copias útiles)
        self.export_graph_artifacts(export_dir=export_dir)

        # guarda copias crudas de edge_index y edge_weight (útiles para reproducibilidad exacta)
        if hasattr(self, "learned_edge_index"):
            np.save(os.path.join(export_dir, "edge_index.npy"), self._to_numpy(self.learned_edge_index))
        if hasattr(self, "last_edge_weight"):
            np.save(os.path.join(export_dir, "edge_weight.npy"), self._to_numpy(self.last_edge_weight))

        # opcional: umbralizar edges.csv para visualización limpia
        if edge_weight_threshold is not None:
            edges_csv = os.path.join(export_dir, "edges.csv")
            if os.path.exists(edges_csv):
                df_edges = pd.read_csv(edges_csv)
                df_edges = df_edges[df_edges["weight"] >= edge_weight_threshold].reset_index(drop=True)
                df_edges.to_csv(edges_csv, index=False)

        # --- 2) Inputs + metadatos
        self.export_input_snapshot(x_input=x_input, x_used=x_used, pestat=pestat, edge_attr=edge_attr,
                                   export_dir=export_dir)

    def export_graph_artifacts(self, export_dir: str):
        """
        Exporta el grafo en formato tabular y ayudas de mapeo:
          - nodes.csv  (id, label, estado, probabilidades, entropías)
          - edges.csv  (source, target, weight, edge_in_prob_v, edge_out_prob_u)
          - mapping.json           (id -> label)
          - states_legend.json     (0..3 -> nombre del estado)

        Requisitos mínimos previos (generados en forward):
          self.learned_edge_index, self.last_edge_weight, self.last_in_probs, self.last_out_probs
        Si falta alguno, la función retorna sin escribir nada.
        """
        try:
            os.makedirs(export_dir, exist_ok=True)
        except Exception:
            pass

        # --- Verificaciones mínimas
        if not (hasattr(self, "learned_edge_index") and
                hasattr(self, "last_edge_weight") and
                hasattr(self, "last_in_probs") and
                hasattr(self, "last_out_probs")):
            # No tenemos datos para exportar el grafo
            return

        # Tensores base (en CPU)
        edge_index = self.learned_edge_index.detach().cpu()
        edge_weight = self.last_edge_weight.detach().cpu()
        in_probs = self.last_in_probs.detach().cpu()  # (N, 2)
        out_probs = self.last_out_probs.detach().cpu()  # (N, 2)

        # =============== NODOS ===============
        # estados: in_bit*2 + out_bit  (0=isolate,1=listen,2=forecast,3=standard)
        in_bit = in_probs.argmax(dim=1)  # (N,)
        out_bit = out_probs.argmax(dim=1)  # (N,)
        states = (in_bit * 2 + out_bit).numpy()

        N = states.shape[0]
        node_ids = np.arange(N)

        # Intentar leer nombres de dispositivo; si algo falla, fallback a node_{i}
        device_names = None
        try:
            client = os.environ.get("CLIENT", "")
            if client:
                devices = pd.read_csv(f"/app/data/{client}/DeviceImport.csv")
                if "name" in devices.columns and len(devices) >= N:
                    device_names = devices["name"].tolist()
        except Exception:
            device_names = None

        labels = device_names if device_names is not None else [f"node_{i}" for i in range(N)]
        labels = np.array(labels, dtype=object)

        # Entropías: si no existen (por ejemplo en eval), rellena con NaN
        if getattr(self, "entropy_in_vec", None) is not None and getattr(self, "entropy_out_vec", None) is not None:
            entropy_in = self.entropy_in_vec.numpy()
            entropy_out = self.entropy_out_vec.numpy()
        else:
            entropy_in = np.full(N, np.nan, dtype=float)
            entropy_out = np.full(N, np.nan, dtype=float)

        nodes_df = pd.DataFrame({
            "node_id": node_ids,
            "label": labels,
            "state": states.astype(int),
            "in_prob": in_probs[:, 1].numpy(),
            "out_prob": out_probs[:, 1].numpy(),
            "entropy_in": entropy_in,
            "entropy_out": entropy_out,
        })
        nodes_df.to_csv(os.path.join(export_dir, "nodes.csv"), index=False)

        # Leyenda de estados
        with open(os.path.join(export_dir, "states_legend.json"), "w") as f:
            json.dump({"0": "isolate", "1": "listen", "2": "forecast", "3": "standard"}, f, indent=2)

        # Mapping id -> label
        mapping = {int(i): str(l) for i, l in zip(node_ids, labels)}
        with open(os.path.join(export_dir, "mapping.json"), "w") as f:
            json.dump(mapping, f, indent=2)

        # =============== ARISTAS DIRIGIDAS ===============
        u = edge_index[0].numpy()
        v = edge_index[1].numpy()
        w = edge_weight.numpy()

        keep_in_prob = in_probs[:, 1].numpy()
        keep_out_prob = out_probs[:, 1].numpy()
        edge_in_prob_v = keep_in_prob[v]
        edge_out_prob_u = keep_out_prob[u]

        edges_df = pd.DataFrame({
            "source": u.astype(int),
            "target": v.astype(int),
            "weight": w,
            "edge_in_prob_v": edge_in_prob_v,
            "edge_out_prob_u": edge_out_prob_u,
        })
        edges_df.to_csv(os.path.join(export_dir, "edges.csv"), index=False)

    def compute_pair_score(self, x: Tensor, edge_index: Adj) -> Tensor:
        """
        Calcula una puntuación par-a-par entre nodos u y v usando sus embeddings.
        x: (N, D)
        edge_index: (2, E)
        """
        u, v = edge_index
        s = self.edge_scorer(x[u], x[v]).squeeze(-1)  # (E,)
        return torch.sigmoid(s / self.pair_temp)  # asegura rango (0,1)

    def _json_friendly(self, v):
        # None, bool, int, float, str -> OK
        if v is None or isinstance(v, (bool, int, float, str)):
            return v
        # Numpy escalares -> convierte a tipos Python
        if isinstance(v, (np.integer,)):
            return int(v)
        if isinstance(v, (np.floating,)):
            return float(v)
        # Enums u objetos con atributo .name
        if hasattr(v, "name") and isinstance(getattr(v, "name"), str):
            return v.name
        # Tipos/clases -> usa su nombre
        if hasattr(v, "__name__"):
            return v.__name__
        # Módulos/clases instanciadas -> usa el nombre de la clase
        return str(v)


