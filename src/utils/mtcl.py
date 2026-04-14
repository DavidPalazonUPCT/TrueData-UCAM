from __future__ import division

import os
import numpy as np
import pandas as pd
import json

import torch
import torch.nn as nn
import torch.nn.functional as F
from .layer import *


class graph_constructor(nn.Module):
    """
        Graph Constructor is responsible for dynamically constructing the adjacency matrix
        based on node embeddings or static features. This is referred to as the Multivariate
        Time Series Correlation Layer (MTCL) in the referenced paper.

        The graph is constructed through a learned embedding space, where each node is embedded
        into a latent dimension (`dim`), and the adjacency matrix is computed based on the similarity
        between node embeddings. If static features are provided, they are used directly to compute
        the adjacency matrix. Otherwise, learned embeddings are used.

        Attributes:
        -----------
        nnodes : int
            Number of nodes in the graph.
        k : int
            Number of nearest neighbors to retain in the graph for each node.
        dim : int
            Dimensionality of the node embeddings.
        device : torch.device
            Device where the model is executed (CPU or GPU).
        alpha : float, default=3
            Scaling factor for the nonlinear transformation of node embeddings.
        static_feat : torch.Tensor, optional
            Static features for each node. If provided, these features are used instead of
            learned embeddings to construct the graph.

        Methods:
        --------
        forward(idx):
            Constructs the adjacency matrix by calculating the similarity between node embeddings.
            It applies a mask to retain only the top-k nearest neighbors for each node.

        fullA(idx):
            Returns the full adjacency matrix without applying the top-k masking, based on the
            learned or static node features.
    """
    def __init__(self, nnodes, k, dim, device, alpha=3, static_feat=None):
        """
            Initializes the Graph Constructor with node embeddings or static features.

            Parameters:
            -----------
            nnodes : int
                Number of nodes in the graph.
            k : int
                Number of nearest neighbors to keep for each node.
            dim : int
                Dimensionality of the latent space for node embeddings.
            device : torch.device
                Device to execute the model (CPU or GPU).
            alpha : float, optional
                Scaling factor for the transformation of node embeddings (default is 3).
            static_feat : torch.Tensor, optional
                Static node features, used to construct the adjacency matrix if provided (default is None).
        """
        super(graph_constructor, self).__init__()
        self.nnodes = nnodes
        if static_feat is not None:
            xd = static_feat.shape[1]
            self.lin1 = nn.Linear(xd, dim)
            self.lin2 = nn.Linear(xd, dim)
        else:
            self.emb1 = nn.Embedding(nnodes, dim)
            self.emb2 = nn.Embedding(nnodes, dim)
            self.lin1 = nn.Linear(dim,dim)
            self.lin2 = nn.Linear(dim,dim)

        self.device = device
        self.k = k
        self.dim = dim
        self.alpha = alpha
        self.static_feat = static_feat

    def forward(self, idx):
        """
            Constructs the adjacency matrix using node embeddings or static features and retains only the top-k nearest neighbors.

            Parameters:
            -----------
            idx : torch.Tensor
                Indices of the nodes for which to construct the adjacency matrix.

            Returns:
            --------
            adj : torch.Tensor
                The constructed adjacency matrix with only the top-k nearest neighbors retained.
        """
        if self.static_feat is None:
            nodevec1 = self.emb1(idx)
            nodevec2 = self.emb2(idx)
        else:
            nodevec1 = self.static_feat[idx,:]
            nodevec2 = nodevec1

        nodevec1 = torch.tanh(self.alpha*self.lin1(nodevec1))
        nodevec2 = torch.tanh(self.alpha*self.lin2(nodevec2))

        a = torch.mm(nodevec1, nodevec2.transpose(1,0))-torch.mm(nodevec2, nodevec1.transpose(1,0))
        adj = F.relu(torch.tanh(self.alpha*a))

        mask = torch.zeros(idx.size(0), idx.size(0)).to(self.device)
        mask.fill_(float('0'))
        s1,t1 = (adj + torch.rand_like(adj)*0.01).topk(self.k,1) #rand for numerical stability
        mask.scatter_(1,t1,s1.fill_(1))
        adj = adj*mask
        self.adj = adj
        return adj

    ## Add function that returns the adjacency matrix without the mask
    def fullA(self, idx):
        """
            Constructs and returns the full adjacency matrix without applying the top-k masking.

            Parameters:
            -----------
            idx : torch.Tensor
                Indices of the nodes for which to construct the full adjacency matrix.

            Returns:
            --------
            adj : torch.Tensor
                The full adjacency matrix without masking the top-k neighbors.
        """
        if self.static_feat is None:
            nodevec1 = self.emb1(idx)
            nodevec2 = self.emb2(idx)
        else:
            nodevec1 = self.static_feat[idx,:]
            nodevec2 = nodevec1

        nodevec1 = torch.tanh(self.alpha*self.lin1(nodevec1))
        nodevec2 = torch.tanh(self.alpha*self.lin2(nodevec2))

        a = torch.mm(nodevec1, nodevec2.transpose(1,0))-torch.mm(nodevec2, nodevec1.transpose(1,0))
        adj = F.relu(torch.tanh(self.alpha*a))
        return adj

################## ADDITIONAL GRAPH LEARNING LAYER TO BE POTENTIALLY APPLIED ##################

class graph_constructor_gat(nn.Module):
    """
        A graph construction module using an attention mechanism similar to Graph Attention Networks (GAT).
        The goal of this module is to create an adjacency matrix for a graph, where the weights of the
        connections between nodes are learned through an attention mechanism based on node embeddings
        or static node features.

        Parameters:
        ----------
        nnodes : int
            Number of nodes in the graph.

        dim : int
            Dimensionality of the node embeddings or feature space.

        device : torch.device
            The device on which computations will be performed (CPU or GPU).

        alpha : float, optional
            Scaling factor for the transformation of the node embeddings, default is 3.

        static_feat : torch.Tensor, optional
            Predefined static features of the nodes. If provided, these features are used instead of
            learning embeddings, default is None.

        Attributes:
        ----------
        lin1 : torch.nn.Linear
            Linear transformation for the first node vector when static features are provided.

        lin2 : torch.nn.Linear
            Linear transformation for the second node vector when static features are provided.

        emb1 : torch.nn.Embedding
            Embedding layer for the first node vector when no static features are provided.

        emb2 : torch.nn.Embedding
            Embedding layer for the second node vector when no static features are provided.

        attention_heads : torch.nn.ModuleList
            A list of linear layers representing multiple attention heads used to calculate pairwise
            attention scores between nodes.

        leaky_relu : torch.nn.LeakyReLU
            LeakyReLU activation function used after computing attention scores.

        attention : torch.nn.Linear
            Linear layer to compute the final attention scores for each pair of nodes.

        Methods:
        -------
        forward(idx)
            Given a list of node indices `idx`, computes an adjacency matrix where the edge weights
            between nodes are determined by attention scores.
    """
    def __init__(self, nnodes, dim, device, alpha=3, static_feat=None):
        """
            Initializes the graph constructor with node embeddings or static features and sets up
            the attention mechanism for graph construction.

            Parameters:
            ----------
            nnodes : int
                Number of nodes in the graph.

            dim : int
                Dimensionality of the node embeddings or feature space.

            device : torch.device
                The device on which computations will be performed (CPU or GPU).

            alpha : float, optional
                Scaling factor for the transformation of the node embeddings, default is 3.

            static_feat : torch.Tensor, optional
                Predefined static features of the nodes. If provided, these features are used instead
                of learning embeddings, default is None.
        """
        super(graph_constructor_gat, self).__init__()
        self.nnodes = nnodes
        self.dim = dim
        self.device = device
        self.alpha = alpha
        self.static_feat = static_feat

        if static_feat is not None:
            xd = static_feat.shape[1]
            self.lin1 = nn.Linear(xd, dim)
            self.lin2 = nn.Linear(xd, dim)
        else:
            self.emb1 = nn.Embedding(nnodes, dim)
            self.emb2 = nn.Embedding(nnodes, dim)

        # Attention mechanism parameters
        num_heads = 5
        self.attention_heads = nn.ModuleList([
            nn.Linear(dim * 2, 1, bias=False) for _ in range(num_heads)
        ])
        self.leaky_relu = nn.LeakyReLU(0.2)
        self.attention = nn.Linear(dim * 2, 1)

    def forward(self, idx):
        """
            Forward pass to compute the adjacency matrix using node embeddings or static features
            and attention weights. This adjacency matrix represents the learned relationships between nodes.

            Parameters:
            ----------
            idx : torch.Tensor
                A tensor containing indices of the nodes for which to compute the adjacency matrix.

            Returns:
            --------
            adj : torch.Tensor
                The computed adjacency matrix, where the values represent the attention-based edge
                weights between nodes.
        """
        if self.static_feat is None:
            nodevec1 = self.emb1(idx)
            nodevec2 = self.emb2(idx)
        else:
            # Apply different linear transformations to create variation
            nodevec1 = self.lin1(self.static_feat[idx, :])
            nodevec2 = self.lin2(self.static_feat[idx, :])

        nodevec1 = torch.tanh(self.alpha * nodevec1)
        nodevec2 = torch.tanh(self.alpha * nodevec2)

        # Compute attention weights
        att_input = torch.cat((nodevec1.unsqueeze(1).expand(-1, self.nnodes, -1),
                               nodevec2.unsqueeze(0).expand(self.nnodes, -1, -1)), dim=2)
        att_scores = self.attention(att_input).squeeze(2)
        # Apply a LeakyReLU activation function
        att_scores_relu = self.leaky_relu(att_scores)
        # Apply softmax to get attention weights
        att_weights = F.softmax(att_scores_relu, dim=1)

        # Compute adjacency matrix using attention weights
        adj = torch.zeros(idx.size(0), idx.size(0)).to(self.device)
        for i in range(idx.size(0)):
            adj[i, idx] = att_weights[i]
        self.adj = adj
        return adj

class graph_global(nn.Module):
    """
        A global graph construction module that learns a global adjacency matrix (A)
        for a graph with a fixed number of nodes. The adjacency matrix is parameterized
        and optimized during training. The values in the matrix represent the strengths
        of the connections between nodes and are learned as trainable parameters.

        Parameters:
        ----------
        nnodes : int
            Number of nodes in the graph.

        k : int
            Unused in this implementation but kept for compatibility with other
            graph constructors.

        dim : int
            Unused in this implementation but kept for compatibility with other
            graph constructors.

        device : torch.device
            The device on which the adjacency matrix will be created and updated (CPU or GPU).

        alpha : float, optional
            Unused in this implementation but kept for compatibility with other
            graph constructors, default is 3.

        static_feat : torch.Tensor, optional
            Unused in this implementation but kept for compatibility with other
            graph constructors, default is None.

        Attributes:
        ----------
        A : torch.nn.Parameter
            A trainable adjacency matrix of size (nnodes, nnodes) initialized with
            random values and optimized during training.
    """
    def __init__(self, nnodes, k, dim, device, alpha=3, static_feat=None):
        """
           Initializes the graph_global class by creating a learnable adjacency matrix A.

           Parameters:
           ----------
           nnodes : int
               Number of nodes in the graph.

           k : int
               Unused parameter, kept for compatibility.

           dim : int
               Unused parameter, kept for compatibility.

           device : torch.device
               The device (CPU or GPU) on which the adjacency matrix is allocated.

           alpha : float, optional
               Unused in this implementation, default is 3.

           static_feat : torch.Tensor, optional
               Unused in this implementation, default is None.
        """
        super(graph_global, self).__init__()
        self.nnodes = nnodes
        self.A = nn.Parameter(torch.randn(nnodes, nnodes).to(device), requires_grad=True).to(device)

    def forward(self, idx):
        """
            Forward pass to return the learned adjacency matrix. The adjacency matrix A
            is activated with a ReLU to ensure all values are non-negative, representing
            valid connection weights between nodes.

            Parameters:
            ----------
            idx : torch.Tensor
                Unused parameter, included for compatibility.

            Returns:
            --------
            torch.Tensor
                A non-negative adjacency matrix with learned connection weights between nodes.
        """
        return F.relu(self.A)

class graph_undirected(nn.Module):
    """
        Constructs an undirected graph for a set of nodes based on learnable embeddings
        or static features. This module generates an adjacency matrix by calculating
        the similarity between node representations and masks it to retain only the top-k
        strongest connections for each node.

        Parameters:
        ----------
        nnodes : int
            Number of nodes in the graph.

        k : int
            Number of strongest connections (edges) to retain for each node in the adjacency matrix.

        dim : int
            Dimensionality of the node embeddings or static features.

        device : torch.device
            The device on which the adjacency matrix and embeddings are stored (CPU or GPU).

        alpha : float, optional
            Scaling factor for the node embeddings, default is 3.

        static_feat : torch.Tensor, optional
            Predefined static features for the nodes, default is None. If provided, these
            features will be used instead of learnable embeddings.
    """
    def __init__(self, nnodes, k, dim, device, alpha=3, static_feat=None):
        """
            Initializes the graph_undirected class, creating either node embeddings
            or using static node features to represent nodes.

            Parameters:
            ----------
            nnodes : int
                Number of nodes in the graph.

            k : int
                Number of strongest connections to retain for each node.

            dim : int
                Dimensionality of the node embeddings or static features.

            device : torch.device
                The device on which the module operates (CPU or GPU).

            alpha : float, optional
                Scaling factor for the embeddings, default is 3.

            static_feat : torch.Tensor, optional
                Predefined static features for nodes, default is None. If provided,
                these features are used in place of embeddings.
        """
        super(graph_undirected, self).__init__()
        self.nnodes = nnodes
        if static_feat is not None:
            xd = static_feat.shape[1]
            self.lin1 = nn.Linear(xd, dim)
        else:
            self.emb1 = nn.Embedding(nnodes, dim)
            self.lin1 = nn.Linear(dim,dim)

        self.device = device
        self.k = k
        self.dim = dim
        self.alpha = alpha
        self.static_feat = static_feat

    def forward(self, idx):
        """
            Forward pass to compute the adjacency matrix based on node embeddings or static features.
            The adjacency matrix is masked to retain only the top-k strongest connections
            for each node, ensuring sparsity in the graph.

            Parameters:
            ----------
            idx : torch.Tensor
                A tensor of node indices for which to compute the adjacency matrix.

            Returns:
            --------
            adj : torch.Tensor
                The computed adjacency matrix, where each element represents the strength of
                the connection between two nodes. The matrix is sparse, with only the top-k
                strongest connections retained for each node.
        """
        if self.static_feat is None:
            nodevec1 = self.emb1(idx)
            nodevec2 = self.emb1(idx)
        else:
            nodevec1 = self.static_feat[idx,:]
            nodevec2 = nodevec1

        nodevec1 = torch.tanh(self.alpha*self.lin1(nodevec1))
        nodevec2 = torch.tanh(self.alpha*self.lin1(nodevec2))

        a = torch.mm(nodevec1, nodevec2.transpose(1,0))
        adj = F.relu(torch.tanh(self.alpha*a))
        mask = torch.zeros(idx.size(0), idx.size(0)).to(self.device)
        mask.fill_(float('0'))
        s1,t1 = adj.topk(self.k,1)
        mask.scatter_(1,t1,s1.fill_(1))
        adj = adj*mask
        return adj

class graph_directed(nn.Module):
    """
        Constructs a directed graph for a set of nodes based on learnable embeddings
        or static features. This module generates an adjacency matrix by calculating
        the similarity between node representations and masks it to retain only the top-k
        strongest directed connections for each node.

        Parameters:
        ----------
        nnodes : int
            Number of nodes in the graph.

        k : int
            Number of strongest connections (edges) to retain for each node in the adjacency matrix.

        dim : int
            Dimensionality of the node embeddings or static features.

        device : torch.device
            The device on which the adjacency matrix and embeddings are stored (CPU or GPU).

        alpha : float, optional
            Scaling factor for the node embeddings, default is 3.

        static_feat : torch.Tensor, optional
            Predefined static features for the nodes, default is None. If provided, these
            features will be used instead of learnable embeddings.
    """
    def __init__(self, nnodes, k, dim, device, alpha=3, static_feat=None):
        """
            Initializes the graph_directed class, creating either node embeddings
            or using static node features to represent nodes.

            Parameters:
            ----------
            nnodes : int
                Number of nodes in the graph.

            k : int
                Number of strongest connections to retain for each node.

            dim : int
                Dimensionality of the node embeddings or static features.

            device : torch.device
                The device on which the module operates (CPU or GPU).

            alpha : float, optional
                Scaling factor for the embeddings, default is 3.

            static_feat : torch.Tensor, optional
                Predefined static features for nodes, default is None. If provided,
                these features are used in place of embeddings.
        """
        super(graph_directed, self).__init__()
        self.nnodes = nnodes
        if static_feat is not None:
            xd = static_feat.shape[1]
            self.lin1 = nn.Linear(xd, dim)
            self.lin2 = nn.Linear(xd, dim)
        else:
            self.emb1 = nn.Embedding(nnodes, dim)
            self.emb2 = nn.Embedding(nnodes, dim)
            self.lin1 = nn.Linear(dim,dim)
            self.lin2 = nn.Linear(dim,dim)

        self.device = device
        self.k = k
        self.dim = dim
        self.alpha = alpha
        self.static_feat = static_feat

    def forward(self, idx):
        """
            Forward pass to compute the directed adjacency matrix based on node embeddings or static features.
            The adjacency matrix is masked to retain only the top-k strongest directed connections
            for each node, ensuring sparsity in the graph.

            Parameters:
            ----------
            idx : torch.Tensor
                A tensor of node indices for which to compute the adjacency matrix.

            Returns:
            --------
            adj : torch.Tensor
                The computed directed adjacency matrix, where each element represents the strength of
                the directed connection from one node to another. The matrix is sparse, with only the top-k
                strongest connections retained for each node.
        """
        if self.static_feat is None:
            nodevec1 = self.emb1(idx)
            nodevec2 = self.emb2(idx)
        else:
            nodevec1 = self.static_feat[idx,:]
            nodevec2 = nodevec1

        nodevec1 = torch.tanh(self.alpha*self.lin1(nodevec1))
        nodevec2 = torch.tanh(self.alpha*self.lin2(nodevec2))

        a = torch.mm(nodevec1, nodevec2.transpose(1,0))
        adj = F.relu(torch.tanh(self.alpha*a))
        mask = torch.zeros(idx.size(0), idx.size(0)).to(self.device)
        mask.fill_(float('0'))
        s1,t1 = adj.topk(self.k,1)
        mask.scatter_(1,t1,s1.fill_(1))
        adj = adj*mask
        return adj
