import os
import numpy as np
import pandas as pd

from .layer import *
from .mtcl import graph_constructor, graph_constructor_gat

class stgnn(nn.Module):
    """
        Spatio-Temporal Graph Neural Network (STGNN) model for time-series forecasting using graph convolutions.

        This model integrates spatio-temporal relationships among nodes by combining graph convolutions with
        temporal convolutions. The model is highly configurable, allowing the use of different graph construction
        methods (such as Top-k or GAT-based graph constructors) and supports dilation for temporal convolutions.

        Parameters:
        -----------
        gcn_true : bool
            Whether to use graph convolutions (GCN).
        buildA_true : bool
            Whether to build the adjacency matrix dynamically.
        gcn_depth : int
            Depth of the graph convolution layers.
        num_nodes : int
            Number of nodes in the graph.
        device : torch.device
            The device (CPU or GPU) to run the model on.
        predefined_A : torch.Tensor, optional
            Predefined adjacency matrix, if not building dynamically.
        static_feat : torch.Tensor, optional
            Static features for nodes.
        dropout : float, default=0.3
            Dropout rate for regularization.
        subgraph_size : int, default=20
            Size of the subgraph for the top-k graph constructor.
        node_dim : int, default=40
            Dimensionality of node embeddings.
        dilation_exponential : int, default=1
            Exponential factor for dilating temporal convolutions.
        conv_channels : int, default=32
            Number of convolution channels in temporal convolutions.
        residual_channels : int, default=32
            Number of residual channels in residual connections.
        skip_channels : int, default=64
            Number of skip channels for skip connections.
        end_channels : int, default=128
            Number of channels for the final layers.
        seq_length : int, default=12
            Length of the input sequence (time steps).
        in_dim : int, default=2
            Input feature dimension.
        out_dim : int, default=12
            Output dimension (forecast horizon).
        layers : int, default=3
            Number of temporal convolution layers.
        propalpha : float, default=0.05
            Alpha for GCN propagation.
        tanhalpha : float, default=3
            Alpha for the Tanh activation in graph constructors.
        layer_norm_affline : bool, default=True
            Whether to use element-wise affine transformation in LayerNorm.

        Methods:
        --------
        forward(input, idx=None):
            Forward pass of the model. Computes the output and, during training, the adjacency matrix.

        save_adj():
            Saves the adjacency matrix at specific intervals or if the "model_best" environment variable is set.
            Saves the adjacency matrix as a `.npy` file and a JSON file for external use.
    """
    def __init__(self, gcn_true, buildA_true, gcn_depth, num_nodes, device, predefined_A=None, static_feat=None, dropout=0.3, subgraph_size=20, node_dim=40, dilation_exponential=1, conv_channels=32, residual_channels=32, skip_channels=64, end_channels=128, seq_length=12, in_dim=2, out_dim=12, layers=3, propalpha=0.05, tanhalpha=3, layer_norm_affline=True):
        super(stgnn, self).__init__()
        self.gcn_true = gcn_true
        self.buildA_true = buildA_true
        self.num_nodes = num_nodes
        self.dropout = dropout
        self.predefined_A = predefined_A
        self.filter_convs = nn.ModuleList()
        self.gate_convs = nn.ModuleList()
        self.residual_convs = nn.ModuleList()
        self.skip_convs = nn.ModuleList()
        self.gconv1 = nn.ModuleList()
        self.gconv2 = nn.ModuleList()
        self.norm = nn.ModuleList()
        self.start_conv = nn.Conv2d(in_channels=in_dim,
                                    out_channels=residual_channels,
                                    kernel_size=(1, 1))

        if os.environ["MODEL"] == 'stgnn-topk':
            self.gc = graph_constructor(num_nodes, subgraph_size, node_dim, device, alpha=tanhalpha, static_feat=static_feat)
        elif os.environ["MODEL"] == 'stgnn-gat':
            self.gc = graph_constructor_gat(nnodes=num_nodes, dim=node_dim, device=device, alpha=tanhalpha,
                                        static_feat=static_feat)

        self.seq_length = seq_length
        kernel_size = 7
        if dilation_exponential>1:
            self.receptive_field = int(1+(kernel_size-1)*(dilation_exponential**layers-1)/(dilation_exponential-1))
        else:
            self.receptive_field = layers*(kernel_size-1) + 1

        for i in range(1):
            if dilation_exponential>1:
                rf_size_i = int(1 + i*(kernel_size-1)*(dilation_exponential**layers-1)/(dilation_exponential-1))
            else:
                rf_size_i = i*layers*(kernel_size-1)+1
            new_dilation = 1
            for j in range(1,layers+1):
                if dilation_exponential > 1:
                    rf_size_j = int(rf_size_i + (kernel_size-1)*(dilation_exponential**j-1)/(dilation_exponential-1))
                else:
                    rf_size_j = rf_size_i+j*(kernel_size-1)

                self.filter_convs.append(dilated_inception(residual_channels, conv_channels, dilation_factor=new_dilation))
                self.gate_convs.append(dilated_inception(residual_channels, conv_channels, dilation_factor=new_dilation))
                self.residual_convs.append(nn.Conv2d(in_channels=conv_channels,
                                                    out_channels=residual_channels,
                                                 kernel_size=(1, 1)))
                if self.seq_length>self.receptive_field:
                    self.skip_convs.append(nn.Conv2d(in_channels=conv_channels,
                                                    out_channels=skip_channels,
                                                    kernel_size=(1, self.seq_length-rf_size_j+1)))
                else:
                    self.skip_convs.append(nn.Conv2d(in_channels=conv_channels,
                                                    out_channels=skip_channels,
                                                    kernel_size=(1, self.receptive_field-rf_size_j+1)))

                if self.gcn_true:
                    self.gconv1.append(mixprop(conv_channels, residual_channels, gcn_depth, dropout, propalpha))
                    self.gconv2.append(mixprop(conv_channels, residual_channels, gcn_depth, dropout, propalpha))

                if self.seq_length>self.receptive_field:
                    self.norm.append(LayerNorm((residual_channels, num_nodes, self.seq_length - rf_size_j + 1),elementwise_affine=layer_norm_affline))
                else:
                    self.norm.append(LayerNorm((residual_channels, num_nodes, self.receptive_field - rf_size_j + 1),elementwise_affine=layer_norm_affline))

                new_dilation *= dilation_exponential

        self.layers = layers
        self.end_conv_1 = nn.Conv2d(in_channels=skip_channels,
                                             out_channels=end_channels,
                                             kernel_size=(1,1),
                                             bias=True)
        self.end_conv_2 = nn.Conv2d(in_channels=end_channels,
                                             out_channels=out_dim,
                                             kernel_size=(1,1),
                                             bias=True)
        if self.seq_length > self.receptive_field:
            self.skip0 = nn.Conv2d(in_channels=in_dim, out_channels=skip_channels, kernel_size=(1, self.seq_length), bias=True)
            self.skipE = nn.Conv2d(in_channels=residual_channels, out_channels=skip_channels, kernel_size=(1, self.seq_length-self.receptive_field+1), bias=True)

        else:
            self.skip0 = nn.Conv2d(in_channels=in_dim, out_channels=skip_channels, kernel_size=(1, self.receptive_field), bias=True)
            self.skipE = nn.Conv2d(in_channels=residual_channels, out_channels=skip_channels, kernel_size=(1, 1), bias=True)


        self.idx = torch.arange(self.num_nodes).to(device)


    def forward(self, input, idx=None):
        """
            Forward pass for the Spatio-Temporal Graph Neural Network (STGNN).

            This method processes the input data through a series of temporal and graph convolutions, applying
            residual, skip, and gating mechanisms to capture spatio-temporal dependencies between nodes in the graph.

            Parameters:
            -----------
            input : torch.Tensor
                The input tensor of shape (batch_size, in_channels, num_nodes, seq_length).
                It represents the sequence of node features over time.

            idx : torch.Tensor, optional
                A tensor of node indices to be used for constructing the dynamic adjacency matrix.
                If None, all nodes are used.

            Returns:
            --------
            torch.Tensor
                If in training mode, returns the output tensor after applying all the convolutional layers.
                The shape of the output is (batch_size, out_channels, num_nodes, out_seq_length).

            Tuple[torch.Tensor, torch.Tensor]
                If in evaluation mode (not training), returns a tuple:
                - Output tensor after the convolutional layers.
                - The adjacency matrix (adp) used for graph convolution.

            Raises:
            -------
            AssertionError
                If the input sequence length doesn't match the preset sequence length (self.seq_length).
        """
        seq_len = input.size(3)
        assert seq_len==self.seq_length, 'input sequence length not equal to preset sequence length'

        if self.seq_length<self.receptive_field:
            input = nn.functional.pad(input,(self.receptive_field-self.seq_length,0,0,0))

        if self.gcn_true:
            if self.buildA_true:
                if idx is None:
                    adp = self.gc(self.idx)
                else:
                    adp = self.gc(idx)
            else:
                adp = self.predefined_A
        self.adj = adp
        x = self.start_conv(input)
        skip = self.skip0(F.dropout(input, self.dropout, training=self.training))
        for i in range(self.layers):
            residual = x
            filter = self.filter_convs[i](x)
            filter = torch.tanh(filter)
            gate = self.gate_convs[i](x)
            gate = torch.sigmoid(gate)
            x = filter * gate
            x = F.dropout(x, self.dropout, training=self.training)
            s = x
            s = self.skip_convs[i](s)
            skip = s + skip
            if self.gcn_true:
                x = self.gconv1[i](x, adp) + self.gconv2[i](x, adp.transpose(1,0))
            else:
                x = self.residual_convs[i](x)

            x = x + residual[:, :, :, -x.size(3):]
            if idx is None:
                x = self.norm[i](x,self.idx)
            else:
                x = self.norm[i](x,idx)

        skip = self.skipE(x) + skip
        x = F.relu(skip)
        x = F.relu(self.end_conv_1(x))
        x = self.end_conv_2(x)

        if self.training:
            return x
        else:
            return x, adp
    def save_adj(self):
        """
            Saves the current adjacency matrix (ADJ) to disk and, if specified, uploads it to an ETL process.

            This function checks if the current iteration number is a multiple of 100, and if so, it saves the
            adjacency matrix (self.adj) as a `.npy` file. If the environment variable 'model_best' is set, the adjacency
            matrix is also saved in JSON format with node labels, and potentially uploaded to an ETL system.

            The directory structure is created if it doesn't already exist, and the adjacency matrix is saved
            under '/app/save/{CLIENT}/{sweep_proyect}/ADJ'.

            The function also handles cases where specific sensors (devices) are excluded, and updates the device list accordingly.

            - The adjacency matrix is only saved if the current iteration (os.environ['iter']) is a multiple of 100.
            - The adjacency matrix is saved as both a `.npy` file and, if applicable, a `.json` file.
            - The function assumes that the adjacency matrix (self.adj) is stored as a PyTorch tensor.
        """
        if "model_best" in os.environ:
            adj_np = self.adj.cpu().detach().numpy()
            devices = pd.read_csv(f"/app/data/{os.environ['CLIENT']}/DeviceImport.csv")
            devicelist = devices['name']
            df_adj = pd.DataFrame(adj_np, columns=devicelist)
            df_adj.index = devicelist
            # Save and send adj to ETL
            if os.environ['TASK'] == 're-train':
                os.makedirs(os.path.dirname(f"{os.environ['MODEL_FOLDER_PATH']}_{os.environ['DATE_YMD_HMS']}"), exist_ok=True)
                np.save(f"{os.environ['MODEL_FOLDER_PATH']}_{os.environ['DATE_YMD_HMS']}/ADP_0.npy",adj_np)
                df_adj.to_json(f"{os.environ['MODEL_FOLDER_PATH']}_{os.environ['DATE_YMD_HMS']}/adj.json",orient='index', indent=4)
            else:
                np.save(f"{os.environ['SAVE_FOLDER_PATH']}/ADP_0.npy",adj_np)
                df_adj.to_json(f"{os.environ['SAVE_FOLDER_PATH']}/adj.json",orient='index', indent=4)
            # print("ADJ saved")
        else:
            pass
