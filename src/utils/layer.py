from __future__ import division
import torch
import torch.nn as nn
from torch.nn import init
import numbers
import torch.nn.functional as F


class nconv(nn.Module):
    """
        A neural network layer that performs a convolution operation using an adjacency matrix.

        This class defines a custom convolution layer that applies a graph convolution operation
        on the input tensor `x` using the adjacency matrix `A`. The operation is performed using
        Einstein summation convention, allowing for flexible manipulation of tensor dimensions.

        Methods:
        --------
        forward(x, A):
            Computes the output of the convolution layer given the input tensor and adjacency matrix.
    """
    def __init__(self):
        """
            Initializes the nconv layer.

            This constructor does not take any parameters or initialize any attributes beyond those
            defined in the nn.Module superclass.
        """
        super(nconv,self).__init__()

    def forward(self,x, A):
        """
            Computes the output of the convolution layer.

            This method applies a graph convolution operation on the input tensor `x` using
            the adjacency matrix `A`. The operation aggregates features from neighboring nodes
            based on the provided adjacency structure.

            Parameters:
            -----------
            x : torch.Tensor
                Input tensor with shape (n, c, w, l), where n is the batch size,
                c is the number of channels, w is the width, and l is the length of the input.
            A : torch.Tensor
                Adjacency matrix with shape (v, w), where v is the number of nodes and w
                is the number of nodes in the graph.

            Returns:
            --------
            torch.Tensor
                The output tensor after applying the convolution operation, with shape (n, c, v, l).
        """
        x = torch.einsum('ncwl,vw->ncvl',(x,A))
        return x.contiguous()

class dy_nconv(nn.Module):
    """
        A dynamic neural network layer that performs a convolution operation using a time-dependent adjacency matrix.

        This class defines a custom convolution layer that applies a graph convolution operation
        on the input tensor `x` using the dynamic adjacency matrix `A`. The operation is performed
        using Einstein summation convention, allowing for efficient manipulation of tensor dimensions.

        Methods:
        --------
        forward(x, A):
            Computes the output of the convolution layer given the input tensor and dynamic adjacency matrix.
    """
    def __init__(self):
        """
            Initializes the dy_nconv layer.

            This constructor does not take any parameters or initialize any attributes beyond those
            defined in the nn.Module superclass.
        """
        super(dy_nconv,self).__init__()

    def forward(self,x, A):
        """
            Computes the output of the convolution layer.

            This method applies a graph convolution operation on the input tensor `x` using
            the dynamic adjacency matrix `A`. The operation aggregates features from neighboring nodes
            based on the provided adjacency structure, allowing for dynamic interactions over time.

            Parameters:
            -----------
            x : torch.Tensor
                Input tensor with shape (n, c, v, l), where n is the batch size,
                c is the number of channels, v is the number of nodes in the graph,
                and l is the length of the input sequence.
            A : torch.Tensor
                Dynamic adjacency matrix with shape (n, v, w), where n is the batch size,
                v is the number of nodes, and w is the number of nodes in the graph.

            Returns:
            --------
            torch.Tensor
                The output tensor after applying the convolution operation, with shape (n, c, w, l).
        """
        x = torch.einsum('ncvl,nvwl->ncwl',(x,A))
        return x.contiguous()

class linear(nn.Module):
    """
        A linear transformation layer using a 2D convolution operation with a kernel size of (1, 1).

        This class implements a linear layer that transforms input feature maps by applying a
        convolution operation with a kernel size of (1, 1). It is essentially a wrapper around
        the `Conv2d` layer in PyTorch, allowing for the processing of inputs with multiple channels.

        Attributes:
        -----------
        mlp : torch.nn.Conv2d
            The convolutional layer that performs the linear transformation.

        Methods:
        --------
        forward(x):
            Applies the linear transformation to the input tensor.
    """
    def __init__(self,c_in,c_out,bias=True):
        """
            Initializes the linear layer.

            Parameters:
            -----------
            c_in : int
                Number of input channels for the convolution operation.
            c_out : int
                Number of output channels for the convolution operation.
            bias : bool, optional
                If True, adds a learnable bias to the output. Default is True.
        """
        super(linear,self).__init__()
        self.mlp = torch.nn.Conv2d(c_in, c_out, kernel_size=(1, 1), padding=(0,0), stride=(1,1), bias=bias)

    def forward(self,x):
        """
            Applies the linear transformation to the input tensor.

            This method computes the output of the linear layer by passing the input tensor
            through the convolutional layer.

            Parameters:
            -----------
            x : torch.Tensor
                Input tensor with shape (n, c_in, h, w), where n is the batch size,
                c_in is the number of input channels, and (h, w) are the height and width
                of the input feature maps.

            Returns:
            --------
            torch.Tensor
                The output tensor with shape (n, c_out, h, w), where c_out is the number of
                output channels.
        """
        return self.mlp(x)


class prop(nn.Module):
    """
        Propagation layer that utilizes neighborhood convolution and a multi-layer perceptron.

        This class implements a propagation mechanism that combines input features with
        neighborhood information from the adjacency matrix. It iteratively updates the features
        based on the graph structure, applying a linear transformation at the end.

        Attributes:
        -----------
        nconv : nconv
            An instance of the nconv class for performing neighborhood convolution.
        mlp : linear
            A linear transformation layer that processes the output of the propagation.
        gdep : int
            The number of propagation layers (graph depth).
        dropout : float
            The dropout rate applied to the output features.
        alpha : float
            A mixing coefficient that balances the contribution of the input and
            neighborhood features.

        Methods:
        --------
        forward(x, adj):
            Performs the propagation operation on the input features using the adjacency matrix.
    """
    def __init__(self,c_in,c_out,gdep,dropout,alpha):
        """
            Initializes the propagation layer.

            Parameters:
            -----------
            c_in : int
                Number of input channels (features) for the convolution operation.
            c_out : int
                Number of output channels (features) after the linear transformation.
            gdep : int
                Depth of the graph propagation (number of iterations).
            dropout : float
                The dropout rate to apply to the output features.
            alpha : float
                Mixing coefficient that balances input features and propagated features.
        """
        super(prop, self).__init__()
        self.nconv = nconv()
        self.mlp = linear(c_in,c_out)
        self.gdep = gdep
        self.dropout = dropout
        self.alpha = alpha

    def forward(self,x,adj):
        """
            Performs the propagation operation on the input features using the adjacency matrix.

            This method first augments the adjacency matrix with self-loops and normalizes it.
            It then iteratively updates the input features based on the neighborhood information
            and applies a linear transformation to produce the final output.

            Parameters:
            -----------
            x : torch.Tensor
                Input tensor with shape (n, c_in), where n is the number of nodes and c_in
                is the number of input features.
            adj : torch.Tensor
                Adjacency matrix with shape (n, n) representing the graph structure.

            Returns:
            --------
            torch.Tensor
                The output tensor with shape (n, c_out), where c_out is the number of output
                features after applying the linear transformation.
        """
        adj = adj + torch.eye(adj.size(0)).to(x.device)
        d = adj.sum(1)
        h = x
        dv = d
        a = adj / dv.view(-1, 1)
        for i in range(self.gdep):
            h = self.alpha*x + (1-self.alpha)*self.nconv(h,a)
        ho = self.mlp(h)
        return ho


class mixprop(nn.Module):
    """
        Mixed propagation layer that combines neighborhood convolution with multi-layer perceptron output.

        This class implements a propagation mechanism that mixes input features with features
        obtained from neighborhood information over multiple propagation layers. The final output
        is produced by concatenating features from each propagation step and applying a linear transformation.

        Attributes:
        -----------
        nconv : nconv
            An instance of the nconv class for performing neighborhood convolution.
        mlp : linear
            A linear transformation layer that processes the concatenated output from multiple
            propagation steps.
        gdep : int
            The number of propagation layers (graph depth).
        dropout : float
            The dropout rate applied to the output features.
        alpha : float
            A mixing coefficient that balances the contribution of the input and
            neighborhood features.

        Methods:
        --------
        forward(x, adj):
            Performs the mixed propagation operation on the input features using the adjacency matrix.
    """
    def __init__(self,c_in,c_out,gdep,dropout,alpha):
        """
            Initializes the mixed propagation layer.

            Parameters:
            -----------
            c_in : int
                Number of input channels (features) for the convolution operation.
            c_out : int
                Number of output channels (features) after the linear transformation.
            gdep : int
                Depth of the graph propagation (number of iterations).
            dropout : float
                The dropout rate to apply to the output features.
            alpha : float
                Mixing coefficient that balances input features and propagated features.
        """
        super(mixprop, self).__init__()
        self.nconv = nconv()
        self.mlp = linear((gdep+1) * c_in, c_out)
        self.gdep = gdep
        self.dropout = dropout
        self.alpha = alpha

    def forward(self,x,adj):
        """
            Performs the mixed propagation operation on the input features using the adjacency matrix.

            This method first augments the adjacency matrix with self-loops and normalizes it.
            It then iteratively updates the input features based on the neighborhood information
            over multiple propagation steps, storing features from each step. The final output is
            obtained by concatenating the features from all steps and applying a linear transformation.

            Parameters:
            -----------
            x : torch.Tensor
                Input tensor with shape (n, c_in), where n is the number of nodes and c_in
                is the number of input features.
            adj : torch.Tensor
                Adjacency matrix with shape (n, n) representing the graph structure.

            Returns:
            --------
            torch.Tensor
                The output tensor with shape (n, c_out), where c_out is the number of output
                features after applying the linear transformation.
        """
        # adj normalization
        adj = adj + torch.eye(adj.size(0)).to(x.device)
        d = adj.sum(1)
        h = x
        out = [h]
        a = adj / d.view(-1, 1)
        # graph propagation
        for i in range(self.gdep):
            h = self.alpha * x + (1 - self.alpha) * self.nconv(h,a)  # alpha=0.05
            out.append(h)
        ho = torch.cat(out, dim=1)
        ho = self.mlp(ho)
        return ho


class dy_mixprop(nn.Module):
    """
        Dynamic mixed propagation layer that combines neighborhood convolution with multi-layer perceptron outputs.

        This class implements a dynamic propagation mechanism that leverages two separate
        multi-layer perceptrons (MLPs) for feature transformation, and performs neighborhood
        convolutions to compute two different adjacency matrices. The final output is the sum
        of two transformed features obtained through separate propagation paths.

        Attributes:
        -----------
        nconv : dy_nconv
            An instance of the dy_nconv class for performing dynamic neighborhood convolution.
        mlp1 : linear
            A linear transformation layer for processing the first propagation path's output.
        mlp2 : linear
            A linear transformation layer for processing the second propagation path's output.
        gdep : int
            The number of propagation layers (graph depth) for each path.
        dropout : float
            The dropout rate applied to the output features (not currently used in forward).
        alpha : float
            A mixing coefficient that balances the contribution of the input and
            neighborhood features.
        lin1 : linear
            A linear layer for transforming the input features to the first adjacency representation.
        lin2 : linear
            A linear layer for transforming the input features to the second adjacency representation.

        Methods:
        --------
        forward(x):
            Performs the dynamic mixed propagation operation on the input features.
    """
    def __init__(self,c_in,c_out,gdep,dropout,alpha):
        """
            Initializes the dynamic mixed propagation layer.

            Parameters:
            -----------
            c_in : int
                Number of input channels (features) for the convolution operation.
            c_out : int
                Number of output channels (features) after the linear transformations.
            gdep : int
                Depth of the graph propagation (number of iterations).
            dropout : float
                The dropout rate to apply to the output features (not currently used).
            alpha : float
                Mixing coefficient that balances input features and propagated features.
        """
        super(dy_mixprop, self).__init__()
        self.nconv = dy_nconv()
        self.mlp1 = linear((gdep+1)*c_in,c_out)
        self.mlp2 = linear((gdep+1)*c_in,c_out)

        self.gdep = gdep
        self.dropout = dropout
        self.alpha = alpha
        self.lin1 = linear(c_in,c_in)
        self.lin2 = linear(c_in,c_in)

    def forward(self,x):
        """
            Performs the dynamic mixed propagation operation on the input features.

            This method first transforms the input features using two different linear layers,
            generating two sets of features. It then computes two dynamic adjacency matrices using
            neighborhood convolution and applies the propagation mechanism for the specified number
            of layers (graph depth) using each adjacency matrix. The outputs from both propagation
            paths are linearly transformed and summed to produce the final output.

            Parameters:
            -----------
            x : torch.Tensor
                Input tensor with shape (n, c_in), where n is the number of nodes and c_in
                is the number of input features.

            Returns:
            --------
            torch.Tensor
                The final output tensor with shape (n, c_out), representing the combined features
                from both propagation paths.
        """
        #adj = adj + torch.eye(adj.size(0)).to(x.device)
        #d = adj.sum(1)
        x1 = torch.tanh(self.lin1(x))
        x2 = torch.tanh(self.lin2(x))
        adj = self.nconv(x1.transpose(2,1),x2)
        adj0 = torch.softmax(adj, dim=2)
        adj1 = torch.softmax(adj.transpose(2,1), dim=2)

        h = x
        out = [h]
        for i in range(self.gdep):
            h = self.alpha*x + (1-self.alpha)*self.nconv(h,adj0)
            out.append(h)
        ho = torch.cat(out,dim=1)
        ho1 = self.mlp1(ho)

        h = x
        out = [h]
        for i in range(self.gdep):
            h = self.alpha * x + (1 - self.alpha) * self.nconv(h, adj1)
            out.append(h)
        ho = torch.cat(out, dim=1)
        ho2 = self.mlp2(ho)

        return ho1+ho2

class dilated_1D(nn.Module):
    """
        1D dilated convolution layer designed for processing temporal or sequential data.

        This class implements a dilated convolutional layer that allows for a wider receptive field
        without increasing the number of parameters or the amount of computation. The dilation factor
        controls the spacing between kernel elements, which can help capture long-range dependencies
        in the input data.

        Attributes:
        -----------
        tconv : nn.Conv2d
            A 2D convolutional layer configured to perform dilated convolutions on the input data.
        kernel_set : list of int
            A predefined set of kernel sizes to be used for convolution (currently not utilized in
            this implementation).
        dilation_factor : int
            The factor by which the kernel is dilated, affecting the receptive field of the convolution.

        Methods:
        --------
        forward(input):
            Applies the dilated convolution to the input tensor.
    """
    def __init__(self, cin, cout, dilation_factor=2):
        """
            Initializes the dilated_1D layer.

            Parameters:
            -----------
            cin : int
                Number of input channels (features) for the convolution operation.
            cout : int
                Number of output channels (features) produced by the convolution.
            dilation_factor : int, optional
                The dilation factor for the convolution (default is 2).
        """
        super(dilated_1D, self).__init__()
        self.tconv = nn.ModuleList()
        self.kernel_set = [2,3,6,7]
        self.tconv = nn.Conv2d(cin,cout,(1,7),dilation=(1,dilation_factor))

    def forward(self,input):
        """
            Applies the dilated convolution to the input tensor.

            This method processes the input tensor through the configured dilated convolution layer.

            Parameters:
            -----------
            input : torch.Tensor
                Input tensor with shape (batch_size, cin, height, width), where
                cin is the number of input channels and height is typically 1 for
                1D convolutions.

            Returns:
            --------
            torch.Tensor
                The output tensor with shape (batch_size, cout, height, width),
                representing the transformed features after the convolution.
        """
        x = self.tconv(input)
        return x

class dilated_inception(nn.Module):
    """
        Dilated Inception module for multi-scale feature extraction.

        This class implements an Inception-like structure with dilated convolutions of varying kernel sizes.
        It enables the model to capture features at different temporal scales, enhancing its ability to
        understand complex patterns in sequential data.

        Attributes:
        -----------
        tconv : nn.ModuleList
            A list of 2D convolutional layers with different kernel sizes and a common dilation factor.
        kernel_set : list of int
            A predefined set of kernel sizes for the convolutional operations.

        Methods:
        --------
        forward(input):
            Applies the dilated convolutions to the input tensor and concatenates the results.
    """
    def __init__(self, cin, cout, dilation_factor=2):
        """
            Initializes the dilated_inception layer.

            Parameters:
            -----------
            cin : int
                Number of input channels (features) for the convolution operations.
            cout : int
                Total number of output channels (features) produced by the convolution.
            dilation_factor : int, optional
                The dilation factor for the convolutions (default is 2).
        """
        super(dilated_inception, self).__init__()
        self.tconv = nn.ModuleList()
        self.kernel_set = [2,3,6,7]
        cout = int(cout/len(self.kernel_set))
        for kern in self.kernel_set:
            self.tconv.append(nn.Conv2d(cin,cout,(1,kern),dilation=(1,dilation_factor)))

    def forward(self,input):
        """
            Applies the dilated convolutions to the input tensor.

            This method processes the input tensor through each convolutional layer and concatenates the
            results to form a multi-scale feature representation.

            Parameters:
            -----------
            input : torch.Tensor
                Input tensor with shape (batch_size, cin, height, width), where
                cin is the number of input channels.

            Returns:
            --------
            torch.Tensor
                The output tensor with shape (batch_size, cout, height, width),
                representing the concatenated features after applying the dilated convolutions.
        """
        x = []
        for i in range(len(self.kernel_set)):
            x.append(self.tconv[i](input))
        for i in range(len(self.kernel_set)):
            x[i] = x[i][...,-x[-1].size(3):]
        x = torch.cat(x,dim=1)
        return x

class LayerNorm(nn.Module):
    """
        Layer Normalization module for normalizing inputs across the specified dimensions.

        This class implements layer normalization, which normalizes the input across the specified
        dimensions, helping to stabilize the learning process in neural networks. It can also apply
        learned scaling and shifting factors (affine transformations) if specified.

        Attributes:
        -----------
        normalized_shape : tuple
            The shape of the input tensor that will be normalized. It can be a single integer or a
            sequence of integers, indicating the dimensions to normalize over.
        eps : float
            A small value added to the denominator for numerical stability (default is 1e-5).
        elementwise_affine : bool
            If True, enables learnable parameters (weight and bias) for the layer normalization (default is True).
        weight : nn.Parameter
            The learnable weight parameter of shape normalized_shape, if elementwise_affine is True.
        bias : nn.Parameter
            The learnable bias parameter of shape normalized_shape, if elementwise_affine is True.

        Methods:
        --------
        reset_parameters():
            Initializes the learnable parameters (weight and bias) to default values.

        forward(input, idx):
            Applies layer normalization to the input tensor along the specified dimensions.

        extra_repr():
            Returns a string representation of the layer normalization configuration.
    """
    __constants__ = ['normalized_shape', 'weight', 'bias', 'eps', 'elementwise_affine']
    def __init__(self, normalized_shape, eps=1e-5, elementwise_affine=True):
        """
            Initializes the LayerNorm module.

            Parameters:
            -----------
            normalized_shape : int or tuple
                The shape of the input tensor that will be normalized. If an integer is provided,
                it will be treated as a single dimension.
            eps : float, optional
                A small value added to the denominator for numerical stability (default is 1e-5).
            elementwise_affine : bool, optional
                If True, enables learnable parameters for scaling and shifting the normalized values
                (default is True).
        """
        super(LayerNorm, self).__init__()
        if isinstance(normalized_shape, numbers.Integral):
            normalized_shape = (normalized_shape,)
        self.normalized_shape = tuple(normalized_shape)
        self.eps = eps
        self.elementwise_affine = elementwise_affine
        if self.elementwise_affine:
            self.weight = nn.Parameter(torch.Tensor(*normalized_shape))
            self.bias = nn.Parameter(torch.Tensor(*normalized_shape))
        else:
            self.register_parameter('weight', None)
            self.register_parameter('bias', None)
        self.reset_parameters()


    def reset_parameters(self):
        """
            Initializes the learnable parameters (weight and bias) to default values.

            If elementwise_affine is True, the weight is initialized to ones and the bias to zeros.
        """
        if self.elementwise_affine:
            init.ones_(self.weight)
            init.zeros_(self.bias)

    def forward(self, input, idx):
        """
            Applies layer normalization to the input tensor.

            This method normalizes the input tensor along the specified dimensions and applies
            learnable weight and bias if elementwise_affine is enabled.

            Parameters:
            -----------
            input : torch.Tensor
                The input tensor to be normalized, with shape (..., normalized_shape).
            idx : int
                The index used to select the corresponding weight and bias for the normalization.

            Returns:
            --------
            torch.Tensor
                The normalized output tensor with the same shape as the input tensor.
        """
        if self.elementwise_affine:
            return F.layer_norm(input, tuple(input.shape[1:]), self.weight[:,idx,:], self.bias[:,idx,:], self.eps)
        else:
            return F.layer_norm(input, tuple(input.shape[1:]), self.weight, self.bias, self.eps)

    def extra_repr(self):
        """
            Returns a string representation of the layer normalization configuration.

            This method includes the normalized shape, epsilon, and whether elementwise affine
            parameters are enabled.

            Returns:
            --------
            str
                A formatted string representing the LayerNorm configuration.
        """
        return '{normalized_shape}, eps={eps}, ' \
            'elementwise_affine={elementwise_affine}'.format(**self.__dict__)
