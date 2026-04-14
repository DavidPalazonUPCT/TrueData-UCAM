import torch.nn as nn
from torch_geometric.typing import Adj, OptTensor
from torch import Tensor

from .cognn_helpers import ActionNetArgs
from ..util import move_all_to_device


class ActionNet(nn.Module):
    def __init__(self, action_args: ActionNetArgs):
        """
        Create a model which represents the agent's policy.
        """
        super().__init__()
        self.num_layers = action_args.num_layers
        self.net = action_args.load_net()  # -> List[nn.Module]
        self.dropout = nn.Dropout(action_args.dropout)
        self.act = action_args.act_type.get()

        self.use_norm = True

        if self.use_norm:
            self.norms = nn.ModuleList([
                nn.LayerNorm(action_args.hidden_dim) for _ in range(self.num_layers - 1)
            ])
        else:
            self.norms = nn.ModuleList([nn.Identity() for _ in range(self.num_layers - 1)])

        self._init_weights()

    def _init_weights(self):
        """
        Applies Xavier uniform initialization to all Linear layers inside GNN blocks.
        """
        for layer in self.net:
            for name, module in layer.named_modules():
                if isinstance(module, nn.Linear):
                    nn.init.xavier_uniform_(module.weight)
                    if module.bias is not None:
                        nn.init.zeros_(module.bias)
                elif hasattr(module, 'lin') and isinstance(module.lin, nn.Linear):
                    nn.init.xavier_uniform_(module.lin.weight)
                    if module.lin.bias is not None:
                        nn.init.zeros_(module.lin.bias)

    def forward(self, x: Tensor, edge_index: Adj, env_edge_attr: OptTensor, act_edge_attr: OptTensor) -> Tensor:
        device = x.device
        x, edge_index = move_all_to_device(device, x=x, edge_index=edge_index).values()

        if env_edge_attr is not None:
            env_edge_attr = env_edge_attr.to(device)
        if act_edge_attr is not None:
            act_edge_attr = act_edge_attr.to(device)

        edge_attrs = [env_edge_attr] + (self.num_layers - 1) * [act_edge_attr]
        for idx, (edge_attr, layer) in enumerate(zip(edge_attrs[:-1], self.net[:-1])):
            x = layer(x=x, edge_index=edge_index, edge_attr=edge_attr)
            x = self.norms[idx](x)
            x = self.dropout(x)
            x = self.act(x)
        x = self.net[-1](x=x, edge_index=edge_index, edge_attr=edge_attrs[-1])

        return x
