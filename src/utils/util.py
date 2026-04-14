import pickle
import numpy as np
import pandas as pd
import json
import time
import datetime
import os
import scipy.sparse as sp
import torch
from scipy.sparse import linalg
from torch.autograd import Variable
import re
from collections import Counter


def move_all_to_device(device, **kwargs):
    return {k: (v.to(device) if isinstance(v, torch.Tensor) else v) for k, v in kwargs.items()}


def normal_std(x):
    """
        Computes the unbiased standard deviation of a given array.

        Parameters:
        -----------
        x : array-like
            Input data from which to compute the standard deviation.

        Returns:
        --------
        float
            The unbiased standard deviation of the input data.

        Notes:
        ------
        The standard deviation is calculated using Bessel's correction.
    """
    return x.std() * np.sqrt((len(x) - 1.)/(len(x)))

def set_device():
    """
        Sets the device for PyTorch operations.

        Returns:
        --------
        torch.device
            The device object representing the GPU if available, otherwise the CPU.
    """
    if torch.cuda.is_available():
        device = torch.device("cuda")
    else:
        device = torch.device("cpu")
    if os.environ['TASK'] == 'inference':
        device = torch.device("cpu")
    else:
        pass
    return device

class DataLoaderS(object):
    """
        A data loader for time series data that supports normalization and splitting
        into training, validation, and test sets.

        Parameters:
        -----------
        file_name : str
            The path to the CSV file containing the data.
        train : float
            The proportion of the dataset to use for training.
        valid : float
            The proportion of the dataset to use for validation.
        device : torch.device
            The device (CPU or GPU) for tensor operations.
        horizon : int
            The forecast horizon for the output.
        window : int
            The input window size for the model.
        normalize : int, optional
            The normalization method to use (default is 2).

        Attributes:
        -----------
        train : list
            The training data batches.
        valid : list
            The validation data batches.
        test : list
            The test data batches.
        scale : torch.Tensor
            Scaling factors for the features.
        rse : float
            Root squared error.
        rae : float
            Relative absolute error.
        device : torch.device
            The device for tensor operations.

        Methods:
        --------
        _normalized(normalize):
            Normalizes the dataset based on the specified method.

        _split(train, valid, test):
            Splits the dataset into training, validation, and test sets.

        _batchify(idx_set, horizon):
            Creates batches of input-output pairs for training or validation.

        get_batches(inputs, targets, batch_size, shuffle=True):
            Generates batches of data for training or validation.
    """
    # train and valid is the ratio of training set and validation set. test = 1 - train - valid
    def __init__(self, file_name, train, valid, device, horizon, window, normalize=2):
        self.P = window
        self.h = horizon
        fin = open(file_name)
        self.rawdat = np.loadtxt(fin, delimiter=',')
        self.dat = np.zeros(self.rawdat.shape)
        self.n, self.m = self.dat.shape
        self.normalize = 2
        self.scale = np.ones(self.m)
        self._normalized(normalize)
        self._split(int(train * self.n), int((train + valid) * self.n), self.n)

        self.scale = torch.from_numpy(self.scale).float()
        tmp = self.test[1] * self.scale.expand(self.test[1].size(0), self.m)

        self.scale = self.scale.to(device)
        self.scale = Variable(self.scale)

        self.rse = normal_std(tmp)
        self.rae = torch.mean(torch.abs(tmp - torch.mean(tmp)))

        self.device = device

    def _normalized(self, normalize):
        """
            Normalizes the dataset based on the specified method.

            Parameters:
            -----------
            normalize : int
                The normalization method to apply (0: none, 1: global max, 2: max per sensor).
        """
        # normalized by the maximum value of entire matrix.
        if (normalize == 0):
            self.dat = self.rawdat
        if (normalize == 1):
            self.dat = self.rawdat / np.max(self.rawdat)
        # normlized by the maximum value of each row(sensor).
        if (normalize == 2):
            for i in range(self.m):
                self.scale[i] = np.max(np.abs(self.rawdat[:, i]))
                self.dat[:, i] = self.rawdat[:, i] / np.max(np.abs(self.rawdat[:, i]))

    def _split(self, train, valid, test):
        """
            Splits the dataset into training, validation, and test sets.

            Parameters:
            -----------
            train : int
                The end index for the training set.
            valid : int
                The end index for the validation set.
            test : int
                The total number of samples.
        """
        train_set = range(self.P + self.h - 1, train)
        valid_set = range(train, valid)
        test_set = range(valid, self.n)
        self.train = self._batchify(train_set, self.h)
        self.valid = self._batchify(valid_set, self.h)
        self.test = self._batchify(test_set, self.h)

    def _batchify(self, idx_set, horizon):
        """
            Creates batches of input-output pairs for training or validation.

            Parameters:
            -----------
            idx_set : range
                The indices to create batches from.
            horizon : int
                The forecast horizon.

            Returns:
            --------
            list
                A list containing the input and target tensors.
        """
        n = len(idx_set)
        X = torch.zeros((n, self.P, self.m))
        Y = torch.zeros((n, self.m))
        for i in range(n):
            end = idx_set[i] - self.h + 1
            start = end - self.P
            X[i, :, :] = torch.from_numpy(self.dat[start:end, :])
            Y[i, :] = torch.from_numpy(self.dat[idx_set[i], :])
        return [X, Y]

    def get_batches(self, inputs, targets, batch_size, shuffle=True):
        """
            Generates batches of data for training or validation.

            Parameters:
            -----------
            inputs : torch.Tensor
                The input data tensor.
            targets : torch.Tensor
                The target data tensor.
            batch_size : int
                The size of each batch.
            shuffle : bool, optional
                Whether to shuffle the data (default is True).

            Yields:
            -------
            tuple
                A tuple containing a batch of inputs and targets.
        """
        length = len(inputs)
        if shuffle:
            index = torch.randperm(length)
        else:
            index = torch.LongTensor(range(length))
        start_idx = 0
        while (start_idx < length):
            end_idx = min(length, start_idx + batch_size)
            excerpt = index[start_idx:end_idx]
            X = inputs[excerpt]
            Y = targets[excerpt]
            X = X.to(self.device)
            Y = Y.to(self.device)
            yield Variable(X), Variable(Y)
            start_idx += batch_size

class DataLoaderM(object):
    """
        A data loader that manages datasets in batches for model training.

        Attributes:
        -----------
        batch_size : int
            Number of samples in each batch.
        current_ind : int
            Current index for iterating over batches.
        size : int
            Total size of the data.
        num_batch : int
            Total number of available batches.
        xs : np.ndarray
            Array of input features.
        ys : np.ndarray
            Array of output labels.

        Parameters:
        -----------
        xs : np.ndarray
            Array containing the input features.
        ys : np.ndarray
            Array containing the output labels.
        batch_size : int
            Number of samples in each batch.
        pad_with_last_sample : bool, optional
            If True, pads with the last sample to make the total size divisible by batch_size. Default is True.

        Methods:
        --------
        shuffle():
            Randomly shuffles the samples in xs and ys.
        get_iterator():
            Returns a generator that produces batches of data.
    """
    def __init__(self, xs, ys, batch_size, pad_with_last_sample=True):
        """
            :param xs:
            :param ys:
            :param batch_size:
            :param pad_with_last_sample: pad with the last sample to make number of samples divisible to batch_size.
        """
        self.batch_size = batch_size
        self.current_ind = 0
        if pad_with_last_sample:
            num_padding = (batch_size - (len(xs) % batch_size)) % batch_size
            x_padding = np.repeat(xs[-1:], num_padding, axis=0)
            y_padding = np.repeat(ys[-1:], num_padding, axis=0)
            xs = np.concatenate([xs, x_padding], axis=0)
            ys = np.concatenate([ys, y_padding], axis=0)
        self.size = len(xs)
        self.num_batch = int(self.size // self.batch_size)
        self.xs = xs
        self.ys = ys

    def shuffle(self):
        """
            Randomly shuffles the samples in xs and ys to ensure that the model
            does not learn any order dependency during training.
        """
        permutation = np.random.permutation(self.size)
        xs, ys = self.xs[permutation], self.ys[permutation]
        self.xs = xs
        self.ys = ys

    def get_iterator(self):
        """
            Returns a generator that produces batches of input-output pairs.

            Yields:
            -------
            tuple
                A tuple containing a batch of input features and corresponding labels.
        """
        self.current_ind = 0
        def _wrapper():
            while self.current_ind < self.num_batch:
                start_ind = self.batch_size * self.current_ind
                end_ind = min(self.size, self.batch_size * (self.current_ind + 1))
                x_i = self.xs[start_ind: end_ind, ...]
                y_i = self.ys[start_ind: end_ind, ...]
                yield (x_i, y_i)
                self.current_ind += 1
        return _wrapper()

class DataLoaderU(object):
    def __init__(self, xs, batch_size, pad_with_last_sample=True):
        """
            Initializes the DataLoader for inference.

            :param xs: Array of input data.
            :param batch_size: The size of each batch.
            :param pad_with_last_sample: Pad with the last sample to make the number of samples divisible by batch_size.
        """
        self.batch_size = batch_size
        self.current_ind = 0

        # Check if padding is needed to make the batch size fit the data
        if pad_with_last_sample:
            num_padding = (batch_size - (len(xs) % batch_size)) % batch_size
            if num_padding > 0:
                x_padding = np.repeat(xs[-1:], num_padding, axis=0)
                xs = np.concatenate([xs, x_padding], axis=0)

        self.size = len(xs)
        self.num_batch = int(self.size // self.batch_size)
        self.xs = xs

    def shuffle(self):
        """
            Shuffles the input data.
        """
        permutation = np.random.permutation(self.size)
        self.xs = self.xs[permutation]

    def get_iterator(self):
        """
            Returns an iterator that yields batches of input data.
        """
        self.current_ind = 0
        def _wrapper():
            while self.current_ind < self.num_batch:
                start_ind = self.batch_size * self.current_ind
                end_ind = min(self.size, self.batch_size * (self.current_ind + 1))
                x_i = self.xs[start_ind:end_ind, ...]
                yield x_i
                self.current_ind += 1
        return _wrapper()


class StandardScaler():
    """
        Standard the input
    """
    def __init__(self, mean, std):
        self.mean = mean
        self.std = std
    def transform(self, data):
        return (data - self.mean) / self.std
    def inverse_transform(self, data):
        return (data * self.std) + self.mean


def sym_adj(adj):
    """
        Symmetrically normalize adjacency matrix.
    """
    adj = sp.coo_matrix(adj)
    rowsum = np.array(adj.sum(1))
    d_inv_sqrt = np.power(rowsum, -0.5).flatten()
    d_inv_sqrt[np.isinf(d_inv_sqrt)] = 0.
    d_mat_inv_sqrt = sp.diags(d_inv_sqrt)
    return adj.dot(d_mat_inv_sqrt).transpose().dot(d_mat_inv_sqrt).astype(np.float32).todense()

def asym_adj(adj):
    """
        Asymmetrically normalize adjacency matrix.
    """
    adj = sp.coo_matrix(adj)
    rowsum = np.array(adj.sum(1)).flatten()
    d_inv = np.power(rowsum, -1).flatten()
    d_inv[np.isinf(d_inv)] = 0.
    d_mat= sp.diags(d_inv)
    return d_mat.dot(adj).astype(np.float32).todense()

def calculate_normalized_laplacian(adj):
    """
        # L = D^-1/2 (D-A) D^-1/2 = I - D^-1/2 A D^-1/2
        # D = diag(A 1)
        :param adj:
        :return:
    """
    adj = sp.coo_matrix(adj)
    d = np.array(adj.sum(1))
    d_inv_sqrt = np.power(d, -0.5).flatten()
    d_inv_sqrt[np.isinf(d_inv_sqrt)] = 0.
    d_mat_inv_sqrt = sp.diags(d_inv_sqrt)
    normalized_laplacian = sp.eye(adj.shape[0]) - adj.dot(d_mat_inv_sqrt).transpose().dot(d_mat_inv_sqrt).tocoo()
    return normalized_laplacian

def calculate_scaled_laplacian(adj_mx, lambda_max=2, undirected=True):
    """
        Computes the scaled Laplacian of a given adjacency matrix.

        Parameters:
        -----------
        adj_mx : numpy.ndarray
            The adjacency matrix of the graph.
        lambda_max : float, optional
            The maximum eigenvalue of the normalized Laplacian. If None, it will be calculated (default is 2).
        undirected : bool, optional
            Whether to treat the graph as undirected. If True, the adjacency matrix will be symmetrized (default is True).

        Returns:
        --------
        numpy.ndarray
            The scaled Laplacian matrix as a dense numpy array.
    """
    if undirected:
        adj_mx = np.maximum.reduce([adj_mx, adj_mx.T])
    L = calculate_normalized_laplacian(adj_mx)
    if lambda_max is None:
        lambda_max, _ = linalg.eigsh(L, 1, which='LM')
        lambda_max = lambda_max[0]
    L = sp.csr_matrix(L)
    M, _ = L.shape
    I = sp.identity(M, format='csr', dtype=L.dtype)
    L = (2 / lambda_max * L) - I
    return L.astype(np.float32).todense()

def load_pickle(pickle_file):
    """
        Loads a pickle file and returns the contained data.

        Parameters:
        -----------
        pickle_file : str
            The path to the pickle file to be loaded.

        Returns:
        --------
        object
            The data contained in the pickle file.

        Raises:
        -------
        Exception
            Raises an exception if the file cannot be loaded due to any error.

        Notes:
        ------
        If a `UnicodeDecodeError` occurs, the file will be attempted to be loaded again
        using 'latin1' encoding to ensure compatibility with different pickle versions.
    """
    try:
        with open(pickle_file, 'rb') as f:
            pickle_data = pickle.load(f)
    except UnicodeDecodeError as e:
        with open(pickle_file, 'rb') as f:
            pickle_data = pickle.load(f, encoding='latin1')
    except Exception as e:
        print('Unable to load data ', pickle_file, ':', e)
        raise
    return pickle_data

def load_adj(pkl_filename):
    """
        Loads the adjacency matrix from a pickle file.

        Parameters:
        -----------
        pkl_filename : str
            The path to the pickle file containing the adjacency matrix data.

        Returns:
        --------
        np.ndarray
            The adjacency matrix loaded from the pickle file.

        Notes:
        ------
        The function also loads sensor IDs and a mapping of sensor IDs to indices,
        but these are not returned.
    """
    sensor_ids, sensor_id_to_ind, adj = load_pickle(pkl_filename)
    return adj

def load_dataset(dataset_dir, batch_size, valid_batch_size=None, test_batch_size=None, scaling_required=True, fraction=0.1):
    """
        Loads a dataset from a specified directory, applies necessary preprocessing,
        and creates data loaders for training, validation, and testing.

        Parameters:
        -----------
        dataset_dir : str
            The directory containing the dataset files.
        batch_size : int
            The size of each training batch.
        valid_batch_size : int, optional
            The size of each validation batch (default is None).
        test_batch_size : int, optional
            The size of each test batch (default is None).
        scaling_required : bool, optional
            Indicates whether to apply scaling to the dataset (default is True).
        fraction : float, optional
            The fraction of data to use for creating subsets (default is 0.1).

        Returns:
        --------
        dict
            A dictionary containing the loaded data, including training, validation,
            and test data loaders, as well as the scaler used for normalization.

        Notes:
        ------
        - The function supports dynamic sensor inclusion and exclusion based on environment
          variables.
        - It handles scaling using `StandardScaler` and can subset the dataset based on
          a specified fraction.
        - Anomaly labels are loaded and processed according to the selected sensors.
        - Sensor selection methods include random sampling, type-based selection, and
          exclusion of specified sensors.
    """
    data = {}
    print(f"dataset directory: {dataset_dir}")
    print(f"Client: {os.environ['CLIENT']}")
    for category in ['train', 'val', 'test']:
        cat_data = np.load(os.path.join(dataset_dir, category + '.npz'))
        data['x_' + category] = cat_data['x']
        data['y_' + category] = cat_data['y']

    devices_path = f"/app/data/{os.environ['CLIENT']}/DeviceImport.csv"
    devices = pd.read_csv(devices_path)
    device_list = devices['name'].to_list()
    os.environ['sensor_list'] = ', '.join(device_list)
    indices_sens_list = devices['name'].index.tolist()
    sens_list = device_list

    data_fix = data.copy()
    if os.environ["TASK"] == "test":
        with open(f"/app/dataloader/CLIENT/{os.environ['CLIENT']}/median_values.json", 'r') as file:
            median_f = json.load(file)
        median_list = [list(item.values())[0] for item in median_f.values()]
        for i, indice in enumerate(indices_sens_list):
            data_fix['x_test'][:, :, indice, :] = median_list[i]
            data_fix['y_test'][:, :, indice, :] = median_list[i]

    data = data_fix.copy()
    sensores_selec = devices.loc[indices_sens_list, 'name']
    if os.environ["TASK"] != "re-train":
        sensores_selec.to_csv(f"/app/data/{os.environ['CLIENT']}/sens_list.csv", index=False)
    os.environ['sensor_list'] = ', '.join(sens_list)

    # Guardar scale_params.csv con min y max por sensor
    try:
        summary_df = pd.read_csv(f"/app/data/{os.environ['CLIENT']}/scale_params.csv")
        os.makedirs(os.environ['SAVE_FOLDER_PATH'], exist_ok=True)
        summary_df.to_csv(f"{os.environ['SAVE_FOLDER_PATH']}/scale_params.csv", index=False)
        print(f"Archivo scale_params.csv guardado en {os.environ['SAVE_FOLDER_PATH']}")
    except Exception as e:
        print(f"[ERROR] No se pudo guardar scale_params.csv: {e}")

    scaler = StandardScaler(mean=data['x_train'][..., 0].mean(), std=data['x_train'][..., 0].std())
    scaler.mean_ = data['x_train'][..., 0].mean()
    scaler.scale_ = data['x_train'][..., 0].std()


    if scaling_required:
        for category in ['train', 'val', 'test']:
            data['x_' + category][..., 0] = scaler.transform(data['x_' + category][..., 0])

    def get_subset(data_x, data_y, fraction):
        total_size = data_x.shape[0]
        #print(f"total: {total_size}")
        #print(f"fraction: {fraction}")
        subset_size = int(total_size * fraction)
        indices = np.random.choice(total_size, subset_size, replace=False)
        subset_x = data_x[indices]
        subset_y = data_y[indices]
        return subset_x, subset_y, indices

    print(f"Data x train shape: {data['x_train'].shape}")
    print(f"Data y train shape: {data['y_train'].shape}")
    train_x_subset, train_y_subset, train_indices = get_subset(data['x_train'], data['y_train'], fraction=fraction)
    val_x_subset, val_y_subset, val_indices = get_subset(data['x_val'], data['y_val'], fraction=fraction)
    test_x_subset, test_y_subset, test_indices = get_subset(data['x_test'], data['y_test'], fraction=fraction)

    data['train_loader'] = DataLoaderM(train_x_subset, train_y_subset, batch_size)
    data['val_loader'] = DataLoaderM(val_x_subset, val_y_subset, valid_batch_size)
    data['test_loader'] = DataLoaderM(test_x_subset, test_y_subset, test_batch_size)

    data['x_train'] = train_x_subset
    data['y_train'] = train_y_subset
    data['x_val'] = val_x_subset
    data['y_val'] = val_y_subset
    data['x_test'] = test_x_subset
    data['y_test'] = test_y_subset

    #print("Data_x_train shape:   ")
    #print(data['x_train'].shape)

    data['scaler'] = scaler

    # Load and subset anomaly labels
    anomaly_labels = np.loadtxt(os.path.join(dataset_dir, 'anomaly_labels.txt'), delimiter=',')
    subset_anomaly_labels = anomaly_labels[test_indices]

    # Save subset of anomaly labels in the desired format
    if os.environ["TASK"] != "re-train":
        os.makedirs(os.environ['SAVE_FOLDER_PATH'], exist_ok=True)
        with open(f"{os.environ['SAVE_FOLDER_PATH']}/subset_anomaly_labels.txt", 'w') as f:
            f.write(','.join(f'{label:.1f}' for label in subset_anomaly_labels))
    else:
        with open(os.path.join(dataset_dir, 'subset_anomaly_labels.txt'), 'w') as f:
            f.write(','.join(f'{label:.1f}' for label in subset_anomaly_labels))
    return data

def masked_mse(preds, labels, null_val=np.nan):
    """
        Computes the masked mean squared error (MSE) between predictions and labels,
        ignoring specified null values.

        Parameters:
        -----------
        preds : torch.Tensor
            The predicted values.
        labels : torch.Tensor
            The ground truth labels.
        null_val : float, optional
            The value to be masked (default is np.nan).
            Predictions and labels with this value will be ignored in the MSE calculation.

        Returns:
        --------
        torch.Tensor
            The mean squared error computed over non-masked values.

        Notes:
        ------
        - The function creates a mask that identifies valid (non-null) entries in the labels.
        - It computes the MSE only on the entries where labels are valid.
        - The loss is adjusted by the mask to ensure that the mean is computed correctly
          over the number of valid samples.
    """
    if np.isnan(null_val):
        mask = ~torch.isnan(labels)
    else:
        mask = (labels!=null_val)
    mask = mask.float()
    mask /= torch.mean((mask))
    mask = torch.where(torch.isnan(mask), torch.zeros_like(mask), mask)
    loss = (preds-labels)**2
    loss = loss * mask
    loss = torch.where(torch.isnan(loss), torch.zeros_like(loss), loss)
    return torch.mean(loss)

def masked_rmse(preds, labels, null_val=np.nan):
    """
        Computes the masked root mean squared error (RMSE) between predictions and labels,
        ignoring specified null values.

        Parameters:
        -----------
        preds : torch.Tensor
            The predicted values.
        labels : torch.Tensor
            The ground truth labels.
        null_val : float, optional
            The value to be masked (default is np.nan).
            Predictions and labels with this value will be ignored in the RMSE calculation.

        Returns:
        --------
        torch.Tensor
            The root mean squared error computed over non-masked values.

        Notes:
        ------
        - This function utilizes the `masked_mse` function to compute the mean squared error
          and then takes the square root of the result.
        - The RMSE provides a measure of how well the predictions match the labels,
          with a focus on the valid (non-masked) entries.
    """
    return torch.sqrt(masked_mse(preds=preds, labels=labels, null_val=null_val))


def masked_mae(preds, labels, null_val=np.nan):
    """
        Computes the masked mean absolute error (MAE) between predictions and labels,
        ignoring specified null values.

        Parameters:
        -----------
        preds : torch.Tensor
            The predicted values.
        labels : torch.Tensor
            The ground truth labels.
        null_val : float, optional
            The value to be masked (default is np.nan).
            Predictions and labels with this value will be ignored in the MAE calculation.

        Returns:
        --------
        torch.Tensor
            The mean absolute error computed over non-masked values.

        Notes:
        ------
        - This function applies a mask to the inputs based on the specified `null_val`,
          allowing for the exclusion of certain values from the error calculation.
        - The MAE provides a measure of how close predictions are to the actual values,
          focusing only on valid (non-masked) entries.
    """
    if np.isnan(null_val):
        mask = ~torch.isnan(labels)
    else:
        mask = (labels!=null_val)
    mask = mask.float()
    mask /=  torch.mean((mask))
    mask = torch.where(torch.isnan(mask), torch.zeros_like(mask), mask)
    loss = torch.abs(preds-labels)
    loss = loss * mask
    loss = torch.where(torch.isnan(loss), torch.zeros_like(loss), loss)
    return torch.mean(loss)

def masked_mape(preds, labels, null_val=np.nan):
    """
        Computes the masked mean absolute percentage error (MAPE) between predictions and labels,
        ignoring specified null values.

        Parameters:
        -----------
        preds : torch.Tensor
            The predicted values.
        labels : torch.Tensor
            The ground truth labels.
        null_val : float, optional
            The value to be masked (default is np.nan).
            Predictions and labels with this value will be ignored in the MAPE calculation.

        Returns:
        --------
        torch.Tensor
            The mean absolute percentage error computed over non-masked values.

        Notes:
        ------
        - This function applies a mask to the inputs based on the specified `null_val`,
          allowing for the exclusion of certain values from the error calculation.
        - MAPE provides a measure of prediction accuracy as a percentage, focusing only on valid
          (non-masked) entries.
        - Care should be taken with labels that may be zero, as this can lead to division by zero.
    """
    if np.isnan(null_val):
        mask = ~torch.isnan(labels)
    else:
        mask = (labels!=null_val)
    mask = mask.float()
    mask /= torch.mean((mask))
    mask = torch.where(torch.isnan(mask), torch.zeros_like(mask), mask)
    loss = torch.abs(preds-labels)/labels
    loss = loss * mask
    loss = torch.where(torch.isnan(loss), torch.zeros_like(loss), loss)
    return torch.mean(loss)


def metric(pred, real):
    """
        Computes evaluation metrics for model predictions against ground truth values.

        Parameters:
        -----------
        pred : torch.Tensor
            The predicted values from the model.
        real : torch.Tensor
            The actual ground truth values.

        Returns:
        --------
        tuple
            A tuple containing:
            - mae : float
                The masked mean absolute error (MAE). Currently set to None.
            - mape : float
                The masked mean absolute percentage error (MAPE) between predictions and real values.
            - rmse : float
                The masked root mean squared error (RMSE) between predictions and real values.

        Notes:
        ------
        - MAE is currently not computed and is returned as None. Uncomment the relevant line to include it.
        - MAPE and RMSE are computed using the `masked_mape` and `masked_rmse` functions, respectively,
          with a null value of 0.0 to mask specific entries.
    """
    mae = None
    #mae = masked_mae(pred,real,0.0).item()
    mape = masked_mape(pred,real,0.0).item()
    rmse = masked_rmse(pred,real,0.0).item()
    return mae,mape,rmse


def load_node_feature(path):
    """
        Loads node features from a specified file, normalizes them, and converts them to a PyTorch tensor.

        Parameters:
        -----------
        path : str
            The file path to the CSV file containing node features. Each line should contain a node ID followed by its features.

        Returns:
        --------
        torch.Tensor
            A tensor containing the normalized node features, where each row corresponds to a node and each column corresponds to a feature.

        Notes:
        ------
        - The function reads a CSV file where the first column is ignored (assumed to be node IDs).
        - Normalization is performed using Z-score normalization (subtracting the mean and dividing by the standard deviation).
        - The resulting tensor is of type `float`.
    """
    fi = open(path)
    x = []
    for li in fi:
        li = li.strip()
        li = li.split(",")
        e = [float(t) for t in li[1:]]
        x.append(e)
    x = np.array(x)
    mean = np.mean(x,axis=0)
    std = np.std(x,axis=0)
    z = torch.tensor((x-mean)/std,dtype=torch.float)
    return z

def normal_std(x):
    """
        Computes the unbiased standard deviation of a given array.

        Parameters:
        -----------
        x : array-like
            The input array for which to compute the standard deviation. This can be a list, numpy array, or similar structure.

        Returns:
        --------
        float
            The unbiased standard deviation of the input array, calculated using Bessel's correction.

        Notes:
        ------
        - This function adjusts the standard deviation by a factor of "the square root of the fraction where the numerator is N−1
         and the denominator is N" to provide an unbiased estimate.
        - It is important for statistical calculations where a small sample size might lead to underestimation of the population standard deviation.
    """
    return x.std() * np.sqrt((len(x) - 1.) / (len(x)))

def count_folders(directory):
    try:
        # Lista solo carpetas en el directorio especificado
        folders = [name for name in os.listdir(directory) if os.path.isdir(os.path.join(directory, name))]
        return len(folders)
    except FileNotFoundError:
        print(f"The directory '{directory}' does not exist.")
        return 0
    except Exception as e:
        print(f"An error occurred: {e}")
        return 0


def get_latest_model_folder(base_path, model):
    # Listar las carpetas en el directorio base
    folders = [f for f in os.listdir(base_path) if f.startswith(model) and os.path.isdir(os.path.join(base_path, f))]

    if not folders:
        return None  # No hay carpetas

    # Ordenar alfabéticamente (cronológicamente)
    folders.sort()

    # Devolver la última carpeta (la más reciente)
    return os.path.join(base_path, folders[-1])

def make_serializable(data):
    for key, value in data.items():
        if isinstance(value, datetime.datetime):
            data[key] = value.strftime('%Y-%m-%d %H:%M:%S')  # Convierte datetime a string
        elif not isinstance(value, (str, int, float, list, dict, bool, type(None))):
            data[key] = str(value)  # Convierte objetos no serializables a string
    return data

