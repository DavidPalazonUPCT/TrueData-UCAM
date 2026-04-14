import numpy as np
from sklearn.decomposition import PCA
from sklearn.metrics import precision_score, recall_score, roc_auc_score, f1_score, average_precision_score, confusion_matrix
from .util import *
from tqdm import tqdm
import joblib
import boto3
import os
import json
import pandas as pd
import wandb


class anomaly_dd():
    """
        A class for detecting anomalies in time series data using PCA-based reconstruction error.

        This class facilitates the initialization and processing of training, validation, and test observations
        and forecasts. It includes methods for PCA modeling to score anomalies based on reconstruction error,
        along with utilities to save models and results.

        Attributes:
        -----------
        train_obs : np.ndarray
            Array containing training observations.
        val_obs : np.ndarray
            Array containing validation observations.
        test_obs : np.ndarray
            Array containing test observations.
        train_forecast : np.ndarray
            Array containing training forecasts.
        val_forecast : np.ndarray
            Array containing validation forecasts.
        test_forecast : np.ndarray
            Array containing test forecasts.
        window_length : int
            The length of the window for processing time series data. If None, defaults to the combined length of
            training and validation observations.
        batch_size : int
            The size of batches used in processing (default is 512).
        root_cause : bool
            Flag indicating whether root cause analysis is performed (default is False).
        pca_model_obj : PCA
            The PCA model object used for transformation and inverse transformation of errors.

        Methods:
        --------
        pca_model(val_error, test_error, dim_size=1):
            Fits the PCA model on validation errors and computes reconstruction errors for both validation
            and test datasets.

        scorer(num_components):
            Calculates reconstruction errors for the validation and test sets, applies PCA, normalizes errors,
            and saves the results to specified file paths.

        save_pca_model(filename):
            Saves the fitted PCA model to a specified file using joblib.
    """
    def __init__(self, train_obs, val_obs, test_obs,
                 train_forecast, val_forecast, test_forecast,
                 window_length=None, batch_size=512,root_cause=False):
        """
            Initializes the anomaly detection object with training, validation, and test data.

            Parameters:
            -----------
            train_obs : np.ndarray
                The training observations used for fitting the model.
            val_obs : np.ndarray
                The validation observations used for evaluating the model.
            test_obs : np.ndarray
                The test observations used for final evaluation.
            train_forecast : np.ndarray
                The forecasted values corresponding to the training observations.
            val_forecast : np.ndarray
                The forecasted values corresponding to the validation observations.
            test_forecast : np.ndarray
                The forecasted values corresponding to the test observations.
            window_length : int, optional
                The length of the window for processing time series data. If None, the total length of
                training and validation observations is used (default is None).
            batch_size : int, optional
                The size of the batches used in processing (default is 512).
            root_cause : bool, optional
                Indicates whether root cause analysis should be performed (default is False).
        """
        self.train_obs = train_obs
        self.val_obs = val_obs
        self.test_obs = test_obs
        self.train_forecast = train_forecast
        self.val_forecast = val_forecast
        self.test_forecast = test_forecast
        self.root_cause = root_cause
        if window_length is None:
            self.window_length = len(train_obs)+len(val_obs)
        else:
            self.window_length = window_length
        self.batch_size = batch_size

        if self.root_cause:
            self.val_re_full = None
            self.test_re_full = None

        self.pca_model_obj = None  # To store the PCA model

    def pca_model(self, val_error, test_error, full_data, dim_size=1):
        """
            Fits the PCA model to the validation error and computes reconstruction errors.

            Parameters:
            -----------
            val_error : np.ndarray
                The validation errors used to fit the PCA model.
            test_error : np.ndarray
                The test errors to be evaluated against the PCA model.
            dim_size : int, optional
                The number of dimensions to keep in the PCA model (default is 1).

            Returns:
            --------
            tuple
                A tuple containing the following:
                - val_re : np.ndarray
                    The reconstruction error for validation data.
                - test_re : np.ndarray
                    The reconstruction error for test data.
                - val_re_full : np.ndarray
                    The full reconstruction error for each validation data point.
                - test_re_full : np.ndarray
                    The full reconstruction error for each test data point.
        """
        if dim_size > int(os.environ['subgraph_size']): # Its args.num_nodes if args.subgraph_size > args.num_nodes
            dim_size = int(os.environ['subgraph_size'])
        else:
            pass
        dim_size = int(int(os.environ['NUM_NODES']) * 0.2)
        pca = PCA(n_components=dim_size, svd_solver='full')
        pca.fit(val_error)

        self.pca_model_obj = pca  # Store the PCA model for later use

        transf_val_error = pca.inverse_transform(pca.transform(val_error))
        transf_test_error = pca.inverse_transform(pca.transform(test_error))
        #transf_data_error = pca.inverse_transform(pca.transform(full_data))
        val_re_full = np.absolute(transf_val_error - val_error)
        val_re = val_re_full.sum(axis=1)
        test_re_full = np.absolute(transf_test_error - test_error)
        test_re = test_re_full.sum(axis=1)
        #data_re_full = np.absolute(transf_data_error - full_data)
        #data_re = data_re_full.sum(axis=1)
        #if os.environ["TASK"] != "re-train":
            #np.save(f"/app/save/{os.environ['CLIENT']}/{os.environ['sweep_proyect']}/{os.environ['run_name']}/data_re_full_0.npy",data_re_full)
            #np.save(f"/app/save/{os.environ['CLIENT']}/{os.environ['sweep_proyect']}/{os.environ['run_name']}/data_re_0.npy",data_re)

        return val_re, test_re, val_re_full, test_re_full

    def scorer(self, num_components):
        """
            Calculates reconstruction errors and scores anomalies.

            This method computes the absolute errors for training, validation, and test data,
            normalizes them, and applies PCA to score the anomalies.

            Parameters:
            -----------
            num_components : int
                The number of principal components to use in PCA modeling.

            Returns:
            --------
            tuple
                A tuple containing:
                - realtime_indicator : np.ndarray
                    The reconstruction errors used as a real-time anomaly indicator.
                - anomaly_prediction : np.ndarray
                    A boolean array indicating detected anomalies.
                - val_re : np.ndarray
                    The reconstruction errors for validation data.
        """
        full_obs = np.concatenate((self.train_obs, self.val_obs, self.test_obs), axis=0)
        full_forecast = np.concatenate((self.train_forecast, self.val_forecast, self.test_forecast), axis=0)
        full_abs = np.absolute(full_obs - full_forecast)
        train_abs = np.absolute(self.train_obs - self.train_forecast)
        val_abs = np.absolute(self.val_obs - self.val_forecast)
        test_abs = np.absolute(self.test_obs - self.test_forecast)

        # Root Mean Squared Error
        mask_val = ~np.isnan(self.val_obs)    # Mask null values (NaN)
        mask_test = ~np.isnan(self.test_obs)
        val_rmse = np.sqrt(np.mean((self.val_obs[mask_val] - self.val_forecast[mask_val]) ** 2))
        test_rmse = np.sqrt(np.mean((self.test_obs[mask_test] - self.test_forecast[mask_test]) ** 2))

        os.environ["TEST_RMSE"] = str(test_rmse)
        os.environ["VAL_RMSE"] = str(val_rmse)

        # Full normalization
        median_global, iqr_global = score_normalizer_values(full_abs)
        min_global, max_global = score_normalizer_values_mM(full_abs)
        full_norm = error_normalizer(full_abs, median_global, iqr_global)
        val_norm = error_normalizer(val_abs, median_global, iqr_global)
        test_norm = error_normalizer(test_abs, median_global, iqr_global)
        #print("[DEBUG] Normalization IQR:", median_global.shape, iqr_global.shape)
        #print("[DEBUG] Normalization MinMax:", min_global.shape, max_global.shape)

        ##test_norm = error_normalizer(test_abs)
        # Batch normalization
        #test_norm = error_sw_normalizer(full_abs,self.window_length,self.batch_size,len(self.test_obs))
        #test_norm = normalizar_por_batches(array=test_abs, batch_size=self.batch_size)

        # PCA reconstruction algorithm to score anomaly of each timepoint
        val_re, test_re, val_re_full, test_re_full = self.pca_model(val_norm, test_norm, full_norm, num_components)
        #val_re, test_re, val_re_full, test_re_full = self.pca_model(val_abs, test_abs, num_components)

        os.environ['threshold_best'] = str(np.percentile(test_re, 93))
        device_df = pd.read_csv(f"/app/data/{os.environ['CLIENT']}/DeviceImport.csv")
        device_list = device_df['name'].to_list()
        filter_scores = np.percentile(test_re_full, 98, axis=0) # 2% values would be in the range of >0.5 (save p98)
        df = pd.DataFrame({'name': device_list,'score_max': filter_scores})
        #print(f"[DEBUG] threshold_best: {os.environ['threshold_best']}")
        # Define path base on TASK
        if os.environ["TASK"] == "re-train":
            model_name = os.environ.get("MODEL_NAME", "UnknownModel")
            timestamp = os.environ.get("DATE_YMD_HMS", "UnknownDate")
            save_dir = f"/app/models/{os.environ['CLIENT']}/{model_name}_{timestamp}"
        else:
            sweep = os.environ.get("sweep_proyect", "default_sweep")
            run = os.environ.get("run_name", "default_run")
            save_dir = f"/app/save/{os.environ['CLIENT']}/{sweep}/{run}"

        # Create directory if it doesn't exist
        os.makedirs(save_dir, exist_ok=True)

        # Save files
        #print("[DEBUG] Saving score_max.csv to:", f"{save_dir}/score_max.csv")
        df.to_csv(f"{save_dir}/score_max.csv", index=False)

        if os.environ["TASK"] != "re-train":
            print("Saving scorer results...")
            np.save(f"{save_dir}/test_abs_0.npy", test_abs)
            np.save(f"{save_dir}/test_norm_0.npy", test_norm)
            np.save(f"{save_dir}/test_re_full_0.npy", test_re_full)
            np.save(f"{save_dir}/test_re_0.npy", test_re)
        else:
            print("Saving scorer results...")
            client = os.environ.get("CLIENT", "UnknownClient")
            model_name = os.environ.get("MODEL_NAME", "UnknownModel")
            timestamp = os.environ.get("DATE_YMD_HMS", "UnknownDate")
            save_dir = f"/app/models/{client}/{model_name}_{timestamp}"
            os.makedirs(save_dir, exist_ok=True)
            np.save(f"{save_dir}/test_abs_0.npy", test_abs)
            np.save(f"{save_dir}/test_norm_0.npy", test_norm)
            np.save(f"{save_dir}/test_re_full_0.npy", test_re_full)
            np.save(f"{save_dir}/test_re_0.npy", test_re)

        if self.root_cause:
            self.val_re_full = val_re_full
            self.test_re_full = test_re_full

        # Real Time Indicator and Automatic Classifier
        realtime_indicator = test_re
        anomaly_prediction = test_re > val_re.max()

        return realtime_indicator, anomaly_prediction, val_re

    def save_pca_model(self, filename):
        """
            Saves the PCA model to a specified file.

            Parameters:
            -----------
            filename : str
                The path to the file where the PCA model will be saved.
        """
        #print("[DEBUG] Saving PCA model to:", filename)
        joblib.dump(self.pca_model_obj, filename)
        #s3_client = boto3.client('s3')
        #s3_key = (os.environ['CLIENT'] + '/' +
        #          os.environ['f_Algorithm'] + '/' +
        #          os.environ['f_STGNN'] + '/' +
        #          os.environ['f_All-models'] + '/' +
        #          os.environ['sweep_name'] + '/' +
        #          os.environ['run_name'] + '_pca.pkl')
        #s3_client.put_object(Bucket=os.environ['bucket'],
        #                     Key=s3_key,
        #                     Body=self.pca_model_obj)


def score_normalizer_values(error_mat):
    """ Calculate normalization statistics (median and IQR) and save them in a CSV. """
    import os

    median = np.median(error_mat, axis=0)
    q1 = np.quantile(error_mat, q=0.25, axis=0)
    q3 = np.quantile(error_mat, q=0.75, axis=0)
    iqr = q3 - q1 + 1e-2  # Add small epsilon to avoid division by zero

    df = pd.DataFrame({'median': median, 'iqr': iqr})

    # Rutas adaptadas según tipo de tarea
    task = os.environ.get("TASK", "train")
    client = os.environ.get("CLIENT", "UnknownClient")

    if task == "re-train":
        # Ruta sin wandb
        model_name = os.environ.get("MODEL_NAME", "UnknownModel")
        timestamp = os.environ.get("DATE_YMD_HMS", "UnknownDate")
        save_path = f"/app/models/{client}/{model_name}_{timestamp}"
    else:
        # Ruta con wandb
        sweep = os.environ.get("sweep_proyect", "default_sweep")
        run = os.environ.get("run_name", "default_run")
        save_path = f"/app/save/{client}/{sweep}/{run}"

    # Asegurar carpeta existente
    os.makedirs(save_path, exist_ok=True)

    # Guardar CSV
    #print("[DEBUG] Saved normalization_scores_iqr.csv to:", f"{save_path}/normalization_scores_iqr.csv")
    df.to_csv(f"{save_path}/normalization_scores_iqr.csv", index=False)

    return median, iqr

def score_normalizer_values_mM(error_mat):
    """ Calculate normalization statistics (min and max) and save them in a CSV. """
    import os

    min_vals = np.min(error_mat, axis=0)
    max_vals = np.max(error_mat, axis=0)

    df = pd.DataFrame({'min': min_vals, 'max': max_vals})

    # Detectar el tipo de tarea
    task = os.environ.get("TASK", "train")
    client = os.environ.get("CLIENT", "UnknownClient")

    if task == "re-train":
        model_name = os.environ.get("MODEL_NAME", "UnknownModel")
        timestamp = os.environ.get("DATE_YMD_HMS", "UnknownDate")
        save_path = f"/app/models/{client}/{model_name}_{timestamp}"
    else:
        sweep = os.environ.get("sweep_proyect", "default_sweep")
        run = os.environ.get("run_name", "default_run")
        save_path = f"/app/save/{client}/{sweep}/{run}"

    # Asegurarse de que el directorio exista
    os.makedirs(save_path, exist_ok=True)

    # Guardar CSV
    #print("[DEBUG] Saved normalization_scores_mM.csv to:", f"{save_path}/normalization_scores_mM.csv")
    df.to_csv(f"{save_path}/normalization_scores_mM.csv", index=False)

    return min_vals, max_vals

def load_normalization_stats(type):
    """ Load normalization statistics (median and IQR). """
    if type == "iqr":
        df = pd.read_csv(f"{os.environ['MODEL_FOLDER_PATH']}/normalization_scores_iqr.csv")
        return df['median'].values, df['iqr'].values
    elif type == "mM":
        df = pd.read_csv(f"{os.environ['MODEL_FOLDER_PATH']}/normalization_scores_mM.csv")
        return df['min'].values, df['max'].values

## function to normalize errors
def error_normalizer(error_mat, median_global, iqr_global):
    median_global = median_global.reshape(1, -1)  # (num_nodes,1)
    iqr_global = iqr_global.reshape(1, -1)
    #print(f"median_global shape: {median_global.shape}")
    return (error_mat - median_global) / iqr_global

def error_normalizer_min_max(error_mat, min_vals, max_vals):
    """ Normalize errors using min-max normalization. """
    min_vals = min_vals.reshape(1, -1)  # (num_nodes,1)
    max_vals = max_vals.reshape(1, -1)
    normalized_error = (error_mat - min_vals) / (max_vals - min_vals)
    return normalized_error


def sliding_window(error_mat, window_size):
    """
        Create a sliding window view of the input error matrix.

        This function generates a new array that consists of overlapping slices of the
        input error matrix, allowing for the analysis of data over a specified window size.

        Parameters:
        -----------
        error_mat : np.ndarray
            A 2D array (matrix) where each row represents an observation and each column
            represents a different feature or measurement.

        window_size : int
            The size of the sliding window. It defines how many consecutive rows from
            the input matrix should be included in each window.

        Returns:
        --------
        np.ndarray
            A 3D array where each "slice" along the first dimension corresponds to a window
            of size `window_size` from the input matrix. The shape of the returned array
            will be (number_of_windows, window_size, number_of_features), where
            number_of_windows is determined by the length of `error_mat` minus `window_size`.

        Notes:
        ------
        - The number of resulting windows is equal to (number_of_rows - window_size + 1).
        - This function is particularly useful for preparing data for time series analysis
          or feeding into machine learning models that require sequential input.
    """
    A=np.arange(window_size)[None, :]
    B=np.arange(error_mat.shape[0] - window_size)[:, None]
    C=A+B
    return error_mat[np.arange(window_size)[None, :] + np.arange(error_mat.shape[0] - window_size)[:, None]]


def error_sw_normalizer(error_mat,window_size,batch_size,test_size):
    """
        Normalize error matrix using a sliding window approach with batch processing.

        This function computes a batch-wise normalization of the error matrix using
        a sliding window technique. The normalization is done by calculating the
        median and interquartile range (IQR) within the defined window size for each batch of data.

        Parameters:
        -----------
        error_mat : np.ndarray
            A 2D array where each row represents an observation error across multiple features.

        window_size : int
            The size of the sliding window used to compute the normalization statistics
            (median and IQR).

        batch_size : int
            The number of samples to process in each batch. This helps in managing memory
            and computational load.

        test_size : int
            The total number of test samples in the error matrix that will be used for
            normalization.

        Returns:
        --------
        np.ndarray
            A 2D array of the same shape as `error_mat` containing the normalized error values.
            Each value is normalized based on the median and IQR calculated from the
            sliding windows.

        Notes:
        ------
        - The function processes the error matrix in batches to handle larger datasets efficiently.
        - The normalization is based on the assumption that the error distribution is skewed, hence using
          IQR for scaling.
    """
    data_size = error_mat.shape[0]
    num_batch = int(test_size / batch_size) + 1
    norm_error_mat = []

    # Batch processing
    print('Batch processing to normalize errors')
    for i in tqdm(range(num_batch)):
        # start and end index process for test data
        start_idx = i * batch_size + (data_size - test_size)
        end_idx = (i + 1) * batch_size + (data_size - test_size)
        # batch error and sliding window error
        if window_size >= test_size:
            window_size = test_size
        batch_error_mat = error_mat[start_idx:end_idx, :]
        sw_error_mat = sliding_window(error_mat[(start_idx - window_size):end_idx, :], window_size)
        #start_sw_idx = max(0, start_idx - window_size)
        #sw_error_mat = sliding_window(error_mat[start_sw_idx:end_idx, :], window_size)
        #sw_error_mat = batch_error_mat

        # Calculate normalization of error
        median = np.median(sw_error_mat, axis=1)
        q1 = np.quantile(sw_error_mat, q=0.25, axis=1)
        q3 = np.quantile(sw_error_mat, q=0.75, axis=1)
        iqr = q3 - q1 + 1e-2    # 1e-2 for numerical stability
        # Calculate batch normalization errors
        batch_norm_error = (batch_error_mat - median) / iqr
        norm_error_mat.append(batch_norm_error)
    # Concat all batch processing
    norm_error_mat = np.concatenate(norm_error_mat)

    return norm_error_mat


def calcular_estadisticos_batch(batch):
    """
        Calculate statistical measures for a batch of data.

        This function computes the mean, first quartile (Q1), and third quartile (Q3)
        for each column in the given batch of data. These statistics are useful for
        understanding the distribution of the data across different features.

        Parameters:
        -----------
        batch : np.ndarray
            A 2D array where each row represents an observation and each column
            represents a feature. The data type should be numeric (int or float).

        Returns:
        --------
        tuple
            A tuple containing three elements:
                - media (np.ndarray): The mean of each column in the batch.
                - q1 (np.ndarray): The first quartile (25th percentile) of each column.
                - q3 (np.ndarray): The third quartile (75th percentile) of each column.
        """
    # Calcular la media y los cuartiles 1 y 3 para cada columna del batch
    media = np.mean(batch, axis=0)
    q1 = np.percentile(batch, 25, axis=0)
    q3 = np.percentile(batch, 75, axis=0)
    return media, q1, q3


def normalizar_batch(batch, media, q1, q3):
    """
        Normalize a batch of data using the mean and quartiles.

        This function performs normalization on the input batch based on the provided
        mean, first quartile (Q1), and third quartile (Q3). The normalization is done
        using the Interquartile Range (IQR) to ensure that the resulting values are scaled
        relative to the spread of the data.

        Parameters:
        -----------
        batch : np.ndarray
            A 2D array where each row represents an observation and each column represents
            a feature. The data type should be numeric (int or float).

        media : np.ndarray
            A 1D array containing the mean of each column in the batch.

        q1 : np.ndarray
            A 1D array containing the first quartile (25th percentile) of each column.

        q3 : np.ndarray
            A 1D array containing the third quartile (75th percentile) of each column.

        Returns:
        --------
        np.ndarray
            A 2D array of the same shape as the input batch, containing the normalized values.
    """
    # Normalizar el batch utilizando la media y los cuartiles
    iqr = q3 - q1 + 1e-2  # 1e-2 for numerical stability
    normalizado = (batch - media) / iqr
    return normalizado


def normalizar_por_batches(array, batch_size):
    """
        Normalize an array by processing it in batches.

        This function divides the input array into smaller batches and normalizes each
        batch independently. The normalization is performed using the mean and quartiles
        (Q1 and Q3) calculated from each batch. This approach helps in reducing the
        influence of outliers and improves the stability of the normalization.

        Parameters:
        -----------
        array : np.ndarray
            A 2D array where each row represents an observation and each column represents
            a feature. The data type should be numeric (int or float).

        batch_size : int
            The number of samples to include in each batch for normalization. Should be
            a positive integer.

        Returns:
        --------
        np.ndarray
            A 2D array of the same shape as the input array, containing the normalized values
            from all batches combined.
    """
    # Dividir el array en batches
    num_batches = int(np.ceil(array.shape[0] / batch_size))
    batches_normalizados = []

    for i in range(num_batches):
        start = i * batch_size
        end = min((i + 1) * batch_size, array.shape[0])
        batch = array[start:end]

        # Calcular estadísticos para el batch actual
        media, q1, q3 = calcular_estadisticos_batch(batch)

        # Normalizar el batch y agregarlo a la lista de batches normalizados
        batch_normalizado = normalizar_batch(batch, media, q1, q3)
        batches_normalizados.append(batch_normalizado)

    # Combinar los batches normalizados en un solo array
    array_normalizado = np.concatenate(batches_normalizados)
    return array_normalizado

# Function to sweep values of thresholds
def sweep_threshold(labels, val_re, test_re):
    """
        Sweeps through a range of thresholds to evaluate anomaly detection performance.

        This function calculates various performance metrics for different thresholds based on
        the reconstruction errors from validation and test datasets. It computes metrics such as
        F1 Score, Precision, Recall, False Positive Rate (FPR), and False Negative Rate (FNR),
        and saves the results in JSON format. Additionally, it saves the test reconstruction errors,
        validation reconstruction errors, and ground truth labels as JSON files.

        Parameters:
        -----------
        labels : np.ndarray
            A 1D array of ground truth labels (0 for normal, 1 for anomaly) corresponding
            to the test dataset. The shape should be (n_samples,).

        val_re : np.ndarray
            A 1D array of reconstruction errors for the validation set. The shape should be (n_samples,).

        test_re : np.ndarray
            A 1D array of reconstruction errors for the test set. The shape should be (n_samples,).

        Returns:
        --------
        None
            The function does not return any value. It saves results to JSON files in the specified
            directory.
    """
    #thr_list = os.environ['thr_list'].split(',')
    thr_list = list(range(0, 1000000, 2000))
    gt_labels = labels
    val_max = val_re.max()
    thr_list = [x * val_max for x in thr_list]
    f1_list = []
    prec_list = []
    rec_list = []
    fpr_list = []
    fnr_list = []
    for threshold_v in thr_list:
        anomaly_pred = test_re > threshold_v
        anomaly_pred_int = anomaly_pred.astype(int)
        # Results
        best_f1 = f1_score(gt_labels, anomaly_pred_int)
        best_precision = precision_score(gt_labels, anomaly_pred_int)
        best_recall = recall_score(gt_labels, anomaly_pred_int)
        best_roc = roc_auc_score(gt_labels, anomaly_pred_int)
        cm = confusion_matrix(gt_labels, anomaly_pred_int)
        best_tn, best_fp, best_fn, best_tp = cm.ravel()
        best_fpr = best_fp / (best_fp + best_tn)
        best_fnr = best_fn / (best_fn + best_tp)
        # Append to lists
        f1_list.append(best_f1)
        prec_list.append(best_precision)
        rec_list.append(best_recall)
        fpr_list.append(best_fpr)
        fnr_list.append(best_fnr)
    # Create a dictionary from the lists
    data = {
        'Threshold': thr_list,
        'F1 Score': f1_list,
        'Precision': prec_list,
        'Recall': rec_list,
        'FPR': fpr_list,
        'FNR': fnr_list
    }
    # Save the dictionary as JSON
    #json_data = json.dumps(data, indent=4)
    #with open('/app/results/' + os.environ['CLIENT'] + '/' + os.environ['sweep_proyect'] + '/threshold.json', 'w') as json_file:
    #    json_file.write(json_data)
    #df_test = pd.DataFrame(test_re)
    #df_val = pd.DataFrame(val_re)
    #df_gt = pd.DataFrame(gt_labels)
    #df_test.to_json('/app/results/' + os.environ['CLIENT'] + '/' + os.environ['sweep_proyect'] + '/test.json', indent=4)
    #df_val.to_json('/app/results/' + os.environ['CLIENT'] + '/' + os.environ['sweep_proyect'] + '/val.json', indent=4)
    #df_gt.to_json('/app/results/' + os.environ['CLIENT'] + '/' + os.environ['sweep_proyect'] + '/gt.json', indent=4)
    #print("Data saved to results folder.")
