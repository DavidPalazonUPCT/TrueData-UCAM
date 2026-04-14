import boto3
import os
import io
import torch
import sys

from botocore.exceptions import NoCredentialsError, PartialCredentialsError


def save_s3_model(model_dict, args):
    """
        Uploads the PyTorch model and its associated metadata to an S3 bucket.

        Parameters:
        -----------
        model_dict : dict
            The state dictionary of the model to be saved.
        args : argparse.Namespace
            The arguments containing model and training configurations (e.g., batch_size, learning_rate).

        Returns:
        --------
        str
            Confirmation message indicating that the model was saved in S3.

        Process:
        --------
        - Serializes the model state dictionary into a buffer.
        - Constructs an S3 key based on environment variables (CLIENT, f_Algorithm, f_STGNN, sweep_project, etc.).
        - Metadata such as model configuration (e.g., num_nodes, epochs, dropout) is extracted from `args` and included in the S3 upload.
        - The model and metadata are uploaded to the S3 bucket specified in the 'bucket' environment variable.

        Notes:
        ------
        - The S3 client from `boto3` is used to handle the upload process.
        - Ensure all required environment variables are set before calling this function.
    """
    print("======: Upload model and model's metadata to S3 :=======", flush=True)
    # Serialize the model state dictionary
    model_buffer = io.BytesIO()
    torch.save(model_dict, model_buffer)
    model_buffer.seek(0)  # Reset the buffer position to the beginning
    s3_client = boto3.client('s3')
    s3_key = (f"{os.environ['CLIENT']}/{os.environ['f_Algorithm']}/{os.environ['f_STGNN']}/{os.environ['f_All-models']}/" +
              f"{os.environ['sweep_proyect']}/{os.environ['sweep_name']}/{os.environ['run_name']}.pth")

    metadata = {
        "num_nodes": str(args.num_nodes),
        "batch_size": str(args.batch_size),
        "learning_rate": str(args.learning_rate),
        "weight_decay": str(args.weight_decay),
        "clip": str(args.clip),
        "step_size1": str(args.step_size1),
        "step_size2": str(args.step_size2),
        "epochs": str(args.epochs),
        "dropout": str(args.dropout),
        "dataset_subset_percentage": str(args.dataset_subset_percentage),
        "buildA_true": str(args.buildA_true),
        "propalpha": str(args.propalpha),
        "tanhalpha": str(args.tanhalpha),
        "num_split": str(args.num_split),
        "node_dim": str(args.node_dim),
        "subgraph_size": str(args.subgraph_size),
        "gcn_true": str(args.gcn_true),
        "gcn_depth": str(args.gcn_depth),
        "dilation_exponential": str(args.dilation_exponential),
        "conv_channels": str(args.conv_channels),
        "residual_channels": str(args.residual_channels),
        "skip_channels": str(args.skip_channels),
        "end_channels": str(args.end_channels),
        "layers": str(args.layers),
        "in_dim": str(args.in_dim),
        "seq_in_len": str(args.seq_in_len),
        "seq_out_len": str(args.seq_out_len),
        "pca_compo": str(args.pca_compo),
        "error_batch_size": str(args.error_batch_size),
        "normalization_window": str(args.normalization_window),
        "env_dim": str(args.env_dim),
        "env_num_layers": str(args.env_num_layers),
        "act_dim": str(args.act_dim),
        "act_num_layers": str(args.act_num_layers),
        "dec_num_layers": str(args.dec_num_layers),
        "tau0": str(args.tau0)
    }
    if "new_temp" in os.environ:
        metadata["temp"] = os.environ["new_temp"]
    s3_client.put_object(Bucket=os.environ['bucket'],
                         Key=s3_key,
                         Body=model_buffer.getvalue(),
                         Metadata=metadata)
    return "Model saved in S3"

def download_model_from_s3(s3_path, local_path):
    """
        Downloads a model from an S3 bucket and saves it locally.

        Parameters:
        -----------
        s3_path : str
            The full S3 path (e.g., 's3://bucket_name/path/to/model.pth') from which the model should be downloaded.
        local_path : str
            The local path where the model should be saved (e.g., '/local/directory/model.pth').

        Returns:
        --------
        bool
            Returns True if the download was successful, False if an error occurred.

        Process:
        --------
        - Parses the S3 path to extract the bucket name and key (file path within the bucket).
        - Downloads the file from the S3 bucket to the specified local path using the boto3 S3 client.
        - Handles errors related to missing or incorrect AWS credentials, as well as file download issues.

        Exceptions:
        -----------
        - NoCredentialsError: Raised if AWS credentials are not found.
        - PartialCredentialsError: Raised if incomplete AWS credentials are provided.
        - Other exceptions related to S3 file access (e.g., incorrect path) are caught and handled with an error message.

        Notes:
        ------
        - Ensure valid AWS credentials are set in the environment or credentials file before using this function.
    """
    s3 = boto3.client('s3')
    bucket_name, key = s3_path.replace("s3://", "").split("/", 1)
    try:
        print("Downloading model from S3...")
        sys.stdout.flush()
        s3.download_file(bucket_name, key, local_path)

    except (NoCredentialsError, PartialCredentialsError):
        print("Error: AWS credentials not found.")
        return False
    except IndentationError as e:
        print(f"Error downloading file from S3: {e}")
        return False
    return True

def load_metadata_from_model(s3_path):
    """
        Loads metadata associated with a model stored in an S3 bucket.

        Parameters:
        -----------
        s3_path : str
            The full S3 path (e.g., 's3://bucket_name/path/to/model.pth') to the model whose metadata is to be retrieved.

        Returns:
        --------
        dict
            A dictionary containing the metadata of the model.

        Process:
        --------
        - Connects to S3 using the boto3 client.
        - Extracts the bucket name and key from the provided S3 path.
        - Retrieves the metadata using the `head_object` method.

        Notes:
        ------
        - Ensure that the provided S3 path points to a valid object in the S3 bucket.
        - Requires appropriate AWS permissions to access the object's metadata.
    """
    s3 = boto3.client('s3')
    bucket_name, key = s3_path.replace("s3://", "").split("/", 1)
    response = s3.head_object(Bucket=bucket_name, Key=key)
    config = response["Metadata"]
    return config