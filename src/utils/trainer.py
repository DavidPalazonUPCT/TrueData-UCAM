import torch.optim as optim
import torch
import numpy as np
import math
from .util import *
import wandb
import os

from .utils_cognn.encoders.encoders import PosEncoder
from torch.optim.lr_scheduler import ReduceLROnPlateau


class Trainer():
    def __init__(self, model, lrate, wdecay, clip, step_size, seq_out_len, device, scaler=False, scaling_required=True):
        """
            Initializes the Trainer class for model training and evaluation.

            Parameters:
            -----------
            model : nn.Module
                The model to be trained.

            lrate : float
                Learning rate for the optimizer.

            wdecay : float
                Weight decay (L2 regularization) coefficient.

            clip : float
                Maximum norm for gradient clipping.

            step_size : int
                Number of iterations after which to update the task level.

            seq_out_len : int
                Length of the output sequence to control the model's task level.

            device : torch.device
                The device on which the model and data will be allocated (e.g., CPU or GPU).

            scaler : bool, optional
                Flag indicating whether to use a scaler for output scaling. Default is False.

            scaling_required : bool, optional
                Flag indicating whether scaling is required before predictions. Default is True.
        """
        self.scaler = scaler
        self.model = model
        self.model.to(device)
        self.optimizer = optim.Adam(self.model.parameters(), lr=lrate, weight_decay=wdecay)

        # --- Aceleración en GPU ---
        self.device = device
        self.use_amp = (str(device).startswith("cuda"))
        if self.use_amp:
            torch.backends.cuda.matmul.allow_tf32 = True
        torch.set_float32_matmul_precision("high")
        self.grad_scaler = torch.cuda.amp.GradScaler(enabled=self.use_amp)
        # Caché de edge_index (evita crearlo cada paso)
        self._edge_index_cache = None

        self.scheduler = ReduceLROnPlateau(
            self.optimizer,
            mode="min",
            factor=0.5,
            patience=200,  # o 150
            threshold=1e-3,
            threshold_mode="rel",
            min_lr=0.01*lrate,
            verbose=True
        )

        # self.loss = util.masked_mae
        self.loss = masked_mse
        self.clip = clip
        self.step = step_size
        self.iter = 1
        self.task_level = 1
        self.seq_out_len = seq_out_len
        self.scaling_required = scaling_required

    def _get_edge_index(self, num_nodes: int):
        # fully-connected dirigido sin autoloops, en GPU y cacheado
        if (self._edge_index_cache is not None) and (self._edge_index_cache.size(1) == num_nodes * (num_nodes - 1)):
            return self._edge_index_cache
        idx = torch.arange(num_nodes, device=self.device)
        src = idx.repeat_interleave(num_nodes)
        dst = idx.repeat(num_nodes)
        mask = (src != dst)
        edge_index = torch.stack([src[mask], dst[mask]], dim=0)  # [2, E]
        self._edge_index_cache = edge_index
        return edge_index


    def train(self, input, real_val, idx=None):
        """
            Trains the model on the provided training data.

            Parameters:
            -----------
            input : torch.Tensor
                Sliding window of time series observations.

            real_val : torch.Tensor
                Each observation at time t (ground truth).

            idx : Optional[torch.Tensor], optional
                Optional index tensor for specific model requirements. Default is None.

            Returns:
            --------
            tuple
                A tuple containing the loss (float), mean absolute percentage error (MAPE), and root mean square error (RMSE).
        """
        self.model.train()
        self.optimizer.zero_grad(set_to_none=True)
        with torch.cuda.amp.autocast(enabled=self.use_amp):
            if os.environ['MODEL_NAME'] == 'STGNN':
                output = self.model(input, idx=idx)
                output = output.transpose(1, 3)
            elif os.environ['MODEL_NAME'] == 'COGNN':
                edge_index = self._get_edge_index(num_nodes=input.shape[2])
                batch = 12
                edge_attr = None
                pestat = PosEncoder.NONE
                output, _ = self.model(input, edge_index=edge_index, batch=batch, edge_attr=edge_attr,
                                       edge_ratio_node_mask=None, pestat=pestat)
                output = torch.unsqueeze(output, dim=1)
                output = torch.unsqueeze(output, dim=3)
                output = output.transpose(0, 2)
            else:
                raise ValueError(f"Unknown model type: {os.environ['MODEL']}")
            real = torch.unsqueeze(real_val, dim=1).to(self.device, non_blocking=True)

            predict = output  # loss en escala del modelo

            if self.iter % self.step == 0 and self.task_level <= self.seq_out_len:
                self.task_level += 1

            base_loss = self.loss(predict, real, 0.0)
            loss = base_loss
            # =================== ENTROPY & BUDGET ===================
            H_in = getattr(self.model, "entropy_in_mean_t", None)
            H_out = getattr(self.model, "entropy_out_mean_t", None)

            # Schedule de entropía (explora → neutro → afila)
            if (H_in is not None) and (H_out is not None):
                H = H_in + H_out
                it = int(os.environ['iter'])
                # Fases:   0–600    : coef negativo (max entropía)
                #          600–1200 : rampa lineal a positivo
                #          1200+    : coef positivo (min entropía)
                coef_neg = -3e-3
                coef_pos = +1e-2
                if it <= 600:
                    coef = coef_neg
                elif it <= 1200:
                    t = (it - 600) / 600.0
                    coef = coef_neg + t * (coef_pos - coef_neg)
                else:
                    coef = coef_pos

                loss = loss + coef * H

                '''if self.model.training and int(os.environ['iter']) % int(os.environ['PRINT_EVERY']) == 0:
                    print(
                        f"[ENTROPY] H_in={H_in.item():.4f} H_out={H_out.item():.4f} coef={coef:.6f} base={base_loss.item():.6f}")
    
                if os.environ.get("WANDB_RUN", "false") == "true":
                    wandb.log({
                        "entropy/H_in": float(H_in.detach().cpu()),
                        "entropy/H_out": float(H_out.detach().cpu()),
                        "loss/base": float(base_loss.detach().cpu()),
                        "loss/with_entropy": float(loss.detach().cpu()),
                        "entropy/coef": float(coef),
                    })'''

            # Añade el budget de conectividad si el modelo lo trajo
            aux = getattr(self.model, "_aux", {})
            L_budget = aux.get("L_budget", None)
            if L_budget is not None:
                loss = loss + L_budget  # ya incorpora beta (fuerza) del lado del modelo
                if os.environ.get("WANDB_RUN", "false") == "true":
                    wandb.log({"loss/L_budget": float(L_budget.detach().cpu())})
            # =============================================================

            self.grad_scaler.scale(loss).backward()
            # Recoge métricas de gradientes
            grad_norms = []
            for name, param in self.model.named_parameters():
                if param.requires_grad and param.grad is not None:
                    grad_norms.append(param.grad.norm().item())

            # Si hay gradientes, calcula estadísticas
            '''if grad_norms:
                grad_tensor = torch.tensor(grad_norms)
                grad_min = grad_tensor.min().item()
                grad_max = grad_tensor.max().item()
                grad_mean = grad_tensor.mean().item()
                grad_std = grad_tensor.std().item()
            
                if int(os.environ['iter']) % int(os.environ['PRINT_EVERY']) == 0:
                    log = '[DEBUG][GRADIENTS] mean: {:.4e}, std: {:.4e}, min: {:.4e}, max: {:.4e}'
                    print(log.format(grad_mean, grad_std, grad_min, grad_max), flush=True)
                    if os.environ["WANDB_RUN"] == "true":
                        wandb.log({
                            "Grad_Min": grad_min,
                            "Grad_Max": grad_max,
                            "Grad_Mean": grad_mean,
                            "Grad_Std": grad_std})
            '''
            if self.clip is not None:
                # Unscale antes de clip para que clip actúe en magnitudes reales
                self.grad_scaler.unscale_(self.optimizer)
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), self.clip)
            self.grad_scaler.step(self.optimizer)
            self.grad_scaler.update()

            mape = masked_mape(predict, real, 0.0).item()
            rmse = masked_rmse(predict, real, 0.0).item()
            self.iter += 1
        return loss.item(), mape, rmse

    def eval(self, input, real_val):
        """
            Evaluates the model using the validation set.

            Parameters:
            -----------
            input : torch.Tensor
                Sliding window of time series observations.

            real_val : torch.Tensor
                Each observation at time t (ground truth).

            Returns:
            --------
            tuple
                A tuple containing the loss (float), mean absolute percentage error (MAPE), and root mean square error (RMSE).
        """
        self.model.eval()
        with torch.no_grad(), torch.cuda.amp.autocast(enabled=self.use_amp):
            if os.environ['MODEL_NAME'] == 'STGNN':
                output, _ = self.model(input)
                output = output.transpose(1,3)
            elif os.environ['MODEL_NAME'] == 'COGNN':
                edge_index = self._get_edge_index(num_nodes=input.shape[2])
                batch = 12
                edge_attr = None
                pestat = PosEncoder.NONE
                output, _ = self.model(input, edge_index=edge_index, batch=batch, edge_attr=edge_attr,
                                       edge_ratio_node_mask=None, pestat=pestat)
                output = torch.unsqueeze(output, dim=1)
                output = torch.unsqueeze(output, dim=3)
                output = output.transpose(0, 2).to(self.device)

            real = torch.unsqueeze(real_val, dim=1)

            predict = output  # loss en escala del modelo

            loss = self.loss(predict, real, 0.0)
            mape = masked_mape(predict, real, 0.0).item()
            rmse = masked_rmse(predict, real, 0.0).item()
            if os.environ["WANDB_RUN"] == "true":
                wandb.log({"Val_loss": loss,
                           "Val_mape": mape,
                           "Val_rmse": rmse
                           })

        return loss.item(), mape, rmse

    def pred(self, input):
        """
            Performs inference on test data for anomaly detection.

            Parameters:
            -----------
            input : torch.Tensor
                Sliding window of time series observations.

            Returns:
            --------
            tuple
                A tuple containing the output (predictions) and learned adjacency matrix (for CoGNN).
        """
        self.model.eval()
        with torch.no_grad(), torch.cuda.amp.autocast(enabled=self.use_amp):
            input = input.to(self.device, non_blocking=True)

            if os.environ['MODEL_NAME'] == 'STGNN':
                output, adp = self.model(input)
                #print(f"======================")
                #print(f"[DEBUG] input = {input}")
                #print(f"======================")
                #print(f"[DEBUG] output = {output}")
                return output, adp
            elif os.environ['MODEL_NAME'] == 'COGNN':
                edge_index = self._get_edge_index(num_nodes=input.shape[2])
                batch = 12
                edge_attr = None
                pestat = PosEncoder.NONE
                #print("CHECK 1")
                #print("input: {}".format(input))
                output, _ = self.model(input, edge_index=edge_index, batch=batch, edge_attr=edge_attr,
                                       edge_ratio_node_mask=None, pestat=pestat)
                #print(f"======================")
                #print(f"[DEBUG] input = {input}")
                #print(f"======================")
                #print(f"[DEBUG] output = {output}")

                output = torch.unsqueeze(output, dim=1)
                output = torch.unsqueeze(output, dim=3)
                output = output.transpose(0, 2).to(self.device)
                return output
            else:
                raise ValueError(f"Unknown model type: {os.environ['MODEL']}")


def create_edge_index_fully_connected(num_nodes):
    """
        Creates an edge index for a fully connected graph.

        Parameters:
        -----------
        num_nodes : int
            The number of nodes in the graph.

        Returns:
        --------
        np.ndarray
            A 2D array where each column represents an edge (source, target)
            in the graph, excluding self-loops.
    """
    edges = []
    for i in range(num_nodes):
        for j in range(num_nodes):
            if i != j:  # No incluimos lazos (conexiones de un nodo consigo mismo)
                edges.append([i, j])
    edges = np.array(edges).T
    return edges