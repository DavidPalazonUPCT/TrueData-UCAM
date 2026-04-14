import wandb
import os
import numpy as np
import json

def wandb_set_args(args):
    """
        Updates the model's argument parameters based on values from the active WandB configuration.

        Parameters:
        ------------
        args : argparse.Namespace
            Argument object containing the initial model configurations.

        Returns:
        --------
        None

        Notes:
        ------
        - Modifies the input `args` object by setting its attributes using the corresponding values from `wandb.config`.
        - Loads dataset nodes from the 'train.npz' file to update `args.num_nodes` with the dataset's node shape.
        - Converts specific WandB configuration values (e.g., `buildA_true`, `gcn_true`) to boolean types.
        - The parameters updated include network architecture, learning, subgraph, and PCA components, among others.
    """
    if os.environ["WANDB_RUN"]=="true":
        args.batch_size = wandb.config["batch_size"]
        args.learning_rate = wandb.config["learning_rate"]
        args.weight_decay = wandb.config["weight_decay"]
        args.clip = wandb.config["clip"]
        args.step_size1 = wandb.config["step_size1"]
        args.step_size2 = wandb.config["step_size2"]
        args.epochs = wandb.config["epochs"]
        args.print_every = wandb.config["print_every"]
        args.dropout = wandb.config["dropout"]
        args.dataset_subset_percentage = wandb.config["dataset_subset_percentage"]
        args.buildA_true = bool(wandb.config["buildA_true"])
        args.propalpha = wandb.config["propalpha"]
        args.tanhalpha = wandb.config["tanhalpha"]
        args.num_split = wandb.config["num_split"]
        args.node_dim = wandb.config["node_dim"]
        cat_data = np.load(os.path.join(args.data, 'train.npz'))
        data_nodes = cat_data['x']
        args.num_nodes = data_nodes.shape[2]
        args.subgraph_size = wandb.config["subgraph_size"]
        args.gcn_true = bool(wandb.config["gcn_true"])
        args.gcn_depth = wandb.config["gcn_depth"]
        args.dilation_exponential = wandb.config["dilation_exponential"]
        args.conv_channels = wandb.config["conv_channels"]
        args.residual_channels = wandb.config["residual_channels"]
        args.skip_channels = wandb.config["skip_channels"]
        args.end_channels = wandb.config["end_channels"]
        args.layers = wandb.config["layers"]
        args.in_dim = wandb.config["in_dim"]
        args.seq_in_len = wandb.config["seq_in_len"]
        args.seq_out_len = wandb.config["seq_out_len"]
        args.pca_compo = wandb.config["pca_compo"]
        args.error_batch_size = wandb.config["error_batch_size"]
        args.normalization_window = wandb.config["normalization_window"]
        args.env_dim = wandb.config["env_dim"]
        args.env_num_layers = wandb.config["env_num_layers"]
        args.act_dim = wandb.config["act_dim"]
        args.act_num_layers = wandb.config["act_num_layers"]
        args.dec_num_layers = wandb.config["dec_num_layers"]
        args.tau0 = wandb.config["tau0"]
        args.temp = wandb.config["temp"]
    else:
        os.environ["CLIENT_BASE"] = os.environ["CLIENT"].split('_')[0]
        sweep_config = load_config_file(f"{os.environ['MODEL_FOLDER_PATH']}/model_metadata.json")
        args.batch_size = sweep_config["batch_size"]
        args.learning_rate = sweep_config["learning_rate"]
        args.weight_decay = sweep_config["weight_decay"]
        args.clip = sweep_config["clip"]
        args.step_size1 = sweep_config["step_size1"]
        args.step_size2 = sweep_config["step_size2"]
        args.epochs = sweep_config["epochs"]
        args.print_every = sweep_config["print_every"]
        args.dropout = sweep_config["dropout"]
        args.dataset_subset_percentage = sweep_config["dataset_subset_percentage"]
        args.buildA_true = bool(sweep_config["buildA_true"])
        args.propalpha = sweep_config["propalpha"]
        args.tanhalpha = sweep_config["tanhalpha"]
        args.num_split = sweep_config["num_split"]
        args.node_dim = sweep_config["node_dim"]
        cat_data = np.load(os.path.join(args.data, 'train.npz'))
        data_nodes = cat_data['x']
        args.num_nodes = data_nodes.shape[2]
        args.subgraph_size = sweep_config["subgraph_size"]
        args.gcn_true = bool(sweep_config["gcn_true"])
        args.gcn_depth = sweep_config["gcn_depth"]
        args.dilation_exponential = sweep_config["dilation_exponential"]
        args.conv_channels = sweep_config["conv_channels"]
        args.residual_channels = sweep_config["residual_channels"]
        args.skip_channels = sweep_config["skip_channels"]
        args.end_channels = sweep_config["end_channels"]
        args.layers = sweep_config["layers"]
        args.in_dim = sweep_config["in_dim"]
        args.seq_in_len = sweep_config["seq_in_len"]
        args.seq_out_len = sweep_config["seq_out_len"]
        args.pca_compo = sweep_config["pca_compo"]
        args.error_batch_size = sweep_config["error_batch_size"]
        args.normalization_window = sweep_config["normalization_window"]
        args.env_dim = sweep_config["env_dim"]
        args.env_num_layers = sweep_config["env_num_layers"]
        args.act_dim = sweep_config["act_dim"]
        args.act_num_layers = sweep_config["act_num_layers"]
        args.dec_num_layers = sweep_config["dec_num_layers"]
        args.tau0 = sweep_config["tau0"]
        args.temp = sweep_config["temp"]

def load_config_file(json_file):
    """
        Loads and returns the configuration from a specified JSON file.

        Parameters:
        ------------
        json_file : str
            Path to the JSON file containing the configuration data.

        Returns:
        --------
        config : dict
            Dictionary containing the configuration data loaded from the JSON file.

        Notes:
        ------
        - Opens the specified JSON file in read mode and loads its contents into a dictionary.
        - Ensures the file is properly closed after reading.
    """
    with open(json_file, 'r') as f:
        config = json.load(f)
    f.close()
    return config

def set_sweep_config():
    """
        Sets the WandB sweep configuration by loading parameters from a config file and environment variables.

        Returns:
        --------
        sweep_config : dict
            Dictionary containing the configuration for a WandB sweep, including optimization method, metric, and model hyperparameters.

        Notes:
        ------
        - Loads configuration values from a JSON file located at '/app/config.json'.
        - Populates environment variables required for the sweep and logs into WandB using an API key.
        - The sweep configuration metric is set as 'F1 score' and the goal is to maximize it.
        - The sweep configuration method can be set as 'grid', 'random' or 'bayes'.
        - Hyperparameters such as 'batch_size', 'learning_rate', 'epochs', and network architecture parameters are loaded from the config.
    """
    config_json_wandb = load_config_file('/app/config.json')
    os.environ['Sweep_Name_0'] = config_json_wandb['Sweep_Name']
    os.environ['sweep_proyect'] = os.environ['Sweep_Name_0'].split('-')[1]
    wandb_key = os.environ['WANDB_KEY']
    wandb.login(key=wandb_key, force=True)
    sweep_config = {
        "name": config_json_wandb['Sweep_Name'],
        "method": "bayes",
        # grid, random or bayes
        "metric": {
            "name": "TEST_RMSE",  # Specify the name of the metric you want to optimize (same as wandb.log)
            "goal": "minimize"   # Specify whether you want to maximize or minimize the metric
        },
        "parameters": {
            "type": config_json_wandb["type"],
            "batch_size": config_json_wandb["batch_size"],
            "learning_rate": config_json_wandb["learning_rate"],
            "weight_decay": config_json_wandb["weight_decay"],
            "clip": config_json_wandb["clip"],
            "step_size1": config_json_wandb["step_size1"],
            "step_size2": config_json_wandb["step_size2"],
            "epochs": config_json_wandb["epochs"],
            "print_every": config_json_wandb["print_every"],
            "dropout": config_json_wandb["dropout"],
            "dataset_subset_percentage": config_json_wandb["dataset_subset_percentage"],
            "buildA_true": config_json_wandb["buildA_true"],
            "propalpha": config_json_wandb["propalpha"],
            "tanhalpha": config_json_wandb["tanhalpha"],
            "num_split": config_json_wandb["num_split"],
            "node_dim": config_json_wandb["node_dim"],
            "subgraph_size": config_json_wandb["subgraph_size"],
            "gcn_true": config_json_wandb["gcn_true"],
            "gcn_depth": config_json_wandb["gcn_depth"],
            "dilation_exponential": config_json_wandb["dilation_exponential"],
            "conv_channels": config_json_wandb["conv_channels"],
            "residual_channels": config_json_wandb["residual_channels"],
            "skip_channels": config_json_wandb["skip_channels"],
            "end_channels": config_json_wandb["end_channels"],
            "layers": config_json_wandb["layers"],
            "in_dim": config_json_wandb["in_dim"],
            "seq_in_len": config_json_wandb["seq_in_len"],
            "seq_out_len": config_json_wandb["seq_out_len"],
            "pca_compo": config_json_wandb["pca_compo"],
            "error_batch_size": config_json_wandb["error_batch_size"],
            "normalization_window": config_json_wandb["normalization_window"],
            "env_dim": config_json_wandb["env_dim"],
            "env_num_layers": config_json_wandb["env_num_layers"],
            "act_dim": config_json_wandb["act_dim"],
            "act_num_layers": config_json_wandb["act_num_layers"],
            "dec_num_layers": config_json_wandb["dec_num_layers"],
            "tau0": config_json_wandb["tau0"],
            "temp": config_json_wandb["temp"]
        }}
    return sweep_config