import argparse
import datetime
import io
import os

from utils.util import *
from utils.utils_aws import *
from utils.utils_wandb import *
from utils.trainer import Trainer
from utils.stgnn import stgnn
from utils.cognn import CoGNN
from utils.utils_cognn.cognn_helpers import *
from utils.utils_cognn.metrics import MetricType
from utils.utils_cognn.model import ModelType
from utils.utils_cognn.encoders.encoders import DataSetEncoders, PosEncoder
from utils.anomaly_dd import anomaly_dd
from utils.evaluate import pointwise_evaluation, early_detection_evaluation

import json
import pandas as pd
import wandb


def str_to_bool(value):
    """
        Converts a string or boolean to a boolean value. Supports various string representations for 'True' and 'False'.

        Parameters:
        ------------
        value: str or bool
            The value to convert, either a string ('true', 'false', etc.) or a boolean.

        Returns:
        --------
        bool:
            The converted boolean value.

        Notes:
        ------
        - Case-insensitive string comparison.
        - 'False' values: {'false', 'f', '0', 'no', 'n'}.
        - 'True' values: {'true', 't', '1', 'yes', 'y'}.
        """
    if isinstance(value, bool):
        return value
    if value.lower() in {'false', 'f', '0', 'no', 'n'}:
        return False
    elif value.lower() in {'true', 't', '1', 'yes', 'y'}:
        return True
    raise ValueError(f'{value} is not a valid boolean value')

parser = argparse.ArgumentParser()

# Data and Pre-processing
parser.add_argument('--device', type=str, default='cuda:0', help='')   # cuda:0 for GPU
parser.add_argument('--data', type=str, default='./data/WADI', help='data path')
parser.add_argument('--scaling_required', type=str_to_bool, default=False, help='Whether to scale input for model and inverse scale output from model.')
parser.add_argument('--save', type=str, default='./save/', help='save path')
parser.add_argument('--runs', type=int, default=1, help='number of runs')
parser.add_argument('--save_result',type=str,default='yes',help='path to save forecasting results')

# For evaluation of early detection ability
parser.add_argument('--delays',type=str,default='[0,6,30,60,120,180,360]',help='Early detection delay constraint values') # for WADI/swat every 6 timestamp is a minute

# Training and optimization
parser.add_argument('--batch_size', type=int, default=4, help='batch size')
parser.add_argument('--learning_rate', type=float, default=3e-4, help='learning rate')
parser.add_argument('--weight_decay', type=float, default=0.0001, help='weight decay rate')
parser.add_argument('--clip', type=int, default=10, help='clip')
parser.add_argument('--step_size1', type=int, default=2500, help='step_size')
parser.add_argument('--step_size2', type=int, default=100, help='step_size')
parser.add_argument('--epochs', type=int, default=20, help='')
parser.add_argument('--print_every', type=int, default=1000, help='')
parser.add_argument('--dropout', type=float, default=0.1, help='dropout rate')
parser.add_argument('--dataset_subset_percentage', type=float, default=1.0, help='percentage of dataset to use for training')

## CST-GNN Framework hyper-parameters
# MTCL layer
parser.add_argument('--buildA_true', type=str_to_bool, default=True, help='whether to construct adaptive adjacency matrix')
parser.add_argument('--propalpha', type=float, default=0.1, help='prop alpha in graph module')
parser.add_argument('--tanhalpha', type=float, default=20, help='adj alpha in graph constructor')
parser.add_argument('--num_split', type=int, default=3, help='number of splits for graphs')
parser.add_argument('--node_dim', type=int, default=256, help='dim of nodes')
parser.add_argument('--num_nodes', type=int, default=127, help='number of nodes/variables')
parser.add_argument('--subgraph_size', type=int, default=15, help='k')

# STGNN layer
parser.add_argument('--gcn_true', type=str_to_bool, default=True, help='whether to add graph convolution layer')
parser.add_argument('--gcn_depth', type=int, default=2, help='graph convolution depth')

parser.add_argument('--dilation_exponential', type=int, default=1, help='dilation exponential')
parser.add_argument('--conv_channels', type=int, default=16, help='convolution channels')
parser.add_argument('--residual_channels', type=int, default=16, help='residual channels')
parser.add_argument('--skip_channels', type=int, default=32, help='skip channels')
parser.add_argument('--end_channels', type=int, default=64, help='end channels')

parser.add_argument('--layers', type=int, default=2, help='number of layers')
parser.add_argument('--in_dim', type=int, default=1, help='inputs dimension')
parser.add_argument('--seq_in_len', type=int, default=12, help='input sequence length')
parser.add_argument('--seq_out_len', type=int, default=1, help='output sequence length')   # 1 if one-step forecast

# Graph-based Anomaly Detection
parser.add_argument('--normalization_window',type=int,default=None,help='Window size to normalize forecast error.')
parser.add_argument('--pca_compo',type=int,default=10,help='Number of principal components, L')
parser.add_argument('--error_batch_size',type=int,default=128,help='Batch processing sliding window normalization')

# COGNN parameters
parser.add_argument('--env_dim',type=int,default=12,help='env_dim')
parser.add_argument('--env_num_layers',type=int,default=7,help='env_num_layers')
parser.add_argument('--act_dim',type=int,default=12,help='act_dim')
parser.add_argument('--act_num_layers',type=int,default=9,help='act_num_layers')
parser.add_argument('--dec_num_layers',type=int,default=3,help='dec_num_layers')
parser.add_argument('--tau0',type=float,default=0.05,help='tau0')
parser.add_argument('--temp',type=float,default=0.1,help='temp')

args = parser.parse_args()
torch.set_num_threads(4)
args.delays = list(map(int, args.delays.strip('[]').split(',')))
args.device = set_device()

def main(runid):
    print("==================: Set model :==================", flush=True)
    """
        Selects a model based on the 'MODEL' environment variable and increments the 'run_count' for tracking purposes.
        - Supports the following model types: "stgnn-topk", "stgnn-gat", and "cognn".
        - The 'run_count' environment variable is incremented and stored as a string.
        - The current 'run_count' is saved as 'run_count_0' before updating.
    """
    if os.environ["MODEL"] == "stgnn-topk":
        model_name = "TOPK"
        os.environ['run_count_0'] = os.environ['run_count']
        os.environ['run_count'] = str(int(os.environ['run_count']) + 1)
    elif os.environ["MODEL"] == "stgnn-gat":
        model_name = "GAT"
        os.environ['run_count_0'] = os.environ['run_count']
        os.environ['run_count'] = str(int(os.environ['run_count']) + 1)
    elif os.environ["MODEL"] == "cognn":
        model_name = "COGNN"
        os.environ['run_count_0'] = os.environ['run_count']
        os.environ['run_count'] = str(int(os.environ['run_count']) + 1)
    print("Model: {}".format(model_name))

    if os.environ["TASK"] != "re-train":
        print("=======: Set sweep name and create folder :=======", flush=True)
        """
            Set sweep name:
            Sets the name for the current WandB run based on environment variables and model parameters, including formatting for certain parameters.
            - 'Sweep_Name_0' is split and used to extract parameter names.
            - Float parameters like 'learning_rate', 'eps', and 'weight_decay' are formatted using scientific notation.
            - The final run name includes the model name and 'run_count_0'.
            - If 'method' is set to "bayes", the run name is adjusted to reflect this.
            - The WandB run name and environment variable 'run_name' are updated accordingly.
        """
        run_name_full = os.environ['Sweep_Name_0'].split('-')
        run_param_names = run_name_full[2:]
        os.environ['sweep_name'] = '_'.join(run_param_names)
        run_name = ''
        for n in run_param_names:
            if n in ['learning_rate', 'eps', 'weight_decay']:
                # Scientific notation of float type parameters
                var_value = wandb.config[n]
                var_value_round = "{:.1e}".format(var_value)
                run_name += '_' + n + var_value_round
            else:
                run_name += '_' + n + str(wandb.config[n])

        run_name = run_name + '_' + model_name + '_' + os.environ['run_count_0']
        wandb.log({"MODEL": model_name})
        if os.environ["method"] == "bayes":
            run_name = os.environ["method"] + '_' + model_name + '_' + os.environ['run_count_0']
        os.environ['run_name'] = run_name
        wandb.run.name = os.environ['run_name']
        print("WandB run name: {}".format(os.environ['run_name']))

        """
            Create folder:
            Creates a directory for saving results based on environment variables, if it doesn't already exist.
        """
        os.makedirs(os.path.dirname(f"{args.save}{os.environ['CLIENT']}/{os.environ['sweep_proyect']}/{os.environ['run_name']}"), exist_ok=True)

    np.random.seed(runid)
    torch.manual_seed(runid)
    torch.cuda.manual_seed(runid)
    torch.cuda.manual_seed_all(runid)
    # random.seed(runid)
    os.environ['PYTHONHASHSEED'] = str(runid)

    os.environ['SAVE_FOLDER_PATH'] = f"{args.save}{os.environ['CLIENT']}/{os.environ['sweep_proyect']}/{os.environ['run_name']}"
    os.environ['MODEL_FOLDER_PATH'] = f"/app/models/{os.environ['CLIENT']}/{os.environ['MODEL_NAME']}"
    os.makedirs(os.path.dirname(f"{os.environ['MODEL_FOLDER_PATH']}"), exist_ok=True)

    print("==================: Load data :==================", flush=True)
    """
        load data:
        Loads the dataset, sets device and sensor information, and adjusts subgraph size based on dataset configuration.
        - Uses 'torch.device' to set the computation device.
        - If 'sensor_split' is set to "true", the number of nodes is set from the WandB configuration.
        - Loads data via 'load_dataset', retrieves the scaler and determines 'num_nodes' based on the training data shape.
        - Adjusts 'subgraph_size' to be no larger than the total number of nodes and updates the corresponding environment variable.
    """
    device = torch.device(args.device)

    dataloader = load_dataset(args.data, args.batch_size, args.batch_size, args.batch_size,args.scaling_required, args.dataset_subset_percentage)
    scaler = dataloader['scaler']

    args.num_nodes = int(dataloader['x_train'].shape[2])
    os.environ['NUM_NODES'] = str(args.num_nodes)

    if os.environ["TASK"] != "re-train":
        if wandb.config['subgraph_size'] > args.num_nodes:
            args.subgraph_size = args.num_nodes
    os.environ['subgraph_size'] = str(args.subgraph_size)

    print("==============: Create model object :==============", flush=True)
    print('Device: ', str(args.device))
    """
        Model object:
        Initializes the model based on the type specified in the 'MODEL' environment variable.
        - Supports two model types: "STGNN" and "COGNN".
        - For STGNN, initializes using various parameters including dropout, node dimensions, and subgraph size.
        - For CoGNN, sets up Gumbel and environment arguments, and initializes the model with specific configurations.
    """
    if os.environ['MODEL_NAME'] == 'STGNN':
        model = stgnn(args.gcn_true, args.buildA_true, args.gcn_depth, args.num_nodes,
                  device, predefined_A=None,
                  dropout=args.dropout, subgraph_size=args.subgraph_size,
                  node_dim=args.node_dim,
                  dilation_exponential=args.dilation_exponential,
                  conv_channels=args.conv_channels, residual_channels=args.residual_channels,
                  skip_channels=args.skip_channels, end_channels= args.end_channels,
                  seq_length=args.seq_in_len, in_dim=args.in_dim, out_dim=args.seq_out_len,
                  layers=args.layers, propalpha=args.propalpha, tanhalpha=args.tanhalpha, layer_norm_affline=True)

    elif os.environ['MODEL_NAME'] == 'COGNN':
        """
            To not have matrix shape errors:
            - env_args.env_dim = env_args.in_dim = action_args.hidden_dim = action_args.env_dim
            - env_args.out_dim = batch_size = slide_win
            - act_dim = env_dim = batch_size
        """
        gumbel_args = GumbelArgs(learn_temp=True, temp_model_type=ModelType.GCN, tau0=args.tau0,
                     temp=args.temp, gin_mlp_func=lambda x: x)
        env_args = EnvArgs(model_type=ModelType.GCN, num_layers=args.env_num_layers, env_dim=args.env_dim,
                layer_norm=True, skip=True, batch_norm=False, dropout=args.dropout,
                act_type=ActivationType.RELU, metric_type=MetricType.ACCURACY, in_dim=args.env_dim, out_dim=args.batch_size,
                gin_mlp_func=lambda x: x, dec_num_layers=args.dec_num_layers, pos_enc=PosEncoder.NONE,
                dataset_encoders=DataSetEncoders.NONE)
        action_args = ActionNetArgs(model_type=ModelType.GCN,num_layers=args.act_num_layers,hidden_dim=args.act_dim,
                      dropout=args.dropout,act_type=ActivationType.RELU,env_dim=args.act_dim,gin_mlp_func=lambda x: x)
        pool = get_pool()

        model = CoGNN(
            gumbel_args=gumbel_args, env_args=env_args, action_args=action_args, pool=pool, device=device
        )
    else:
        raise ValueError(f"Unknown model type: {os.environ['MODEL']}")
    print('Created {} model.'.format(os.environ['MODEL_NAME']))

    print("=================: Start training :=================", flush=True)
    """
        Trainer:
        Initializes the Trainer with the specified model and training parameters.
        - The Trainer is set up with parameters including learning rate, weight decay, gradient clipping, 
          step size, output sequence length, device, and data scaler.
        - 'scaling_required' indicates whether data scaling is necessary for training.
    """
    engine = Trainer(model, args.learning_rate, args.weight_decay, args.clip, args.step_size1, args.seq_out_len, device,
                     scaler, args.scaling_required)
    his_loss = []
    val_time = []
    train_time = []
    train_loss_min = 1e6
    best_loss_in_iter = float('inf')
    minl = 1e7

    # Early stop configuration
    early_stop = False
    patience_epoch = 5
    no_improvement_epoch = 0
    best_val_loss_epoch = float('inf')
    patience_iter = 5000  # N° de iteraciones sin mejora antes de detener
    best_train_loss_iter = float('inf')

    # Re-Train
    if os.environ["TASK"] == "re-train":
        if not os.path.exists(f"/app/models/{os.environ['CLIENT']}"):
            os.makedirs(f"/app/models/{os.environ['CLIENT']}")
            print(f"Folder /app/models/{os.environ['CLIENT']} created.")
            os.environ['CLIENT'] = os.environ['CLIENT'].split('_')[0]
            engine.model.load_state_dict(torch.load(f"{os.environ['MODEL_FOLDER_PATH']}/model.pth"))
            print(f"Model {os.environ['CLIENT']}/{os.environ['MODEL_NAME']}/model.pth loaded.")
            os.environ['CLIENT'] = os.environ['CLIENT'] + "_RETRAIN"
            print(f"Change client from {os.environ['CLIENT_BASE']} to {os.environ['CLIENT']}.")
        else:
            model_last_folder = get_latest_model_folder(
                base_path=f"/app/models/{os.environ['CLIENT']}", model=os.environ['MODEL_NAME'])
            engine.model.load_state_dict(torch.load(f"{model_last_folder}/model.pth"))
            print(f"Model {model_last_folder}/model.pth loaded.")

    os.environ['epoch_f'] = str(args.epochs)
    for i in range(1, args.epochs+1):
        """
            Executes the training loop for a specified number of epochs, tracking training metrics.
            - Loops over the number of epochs defined in 'args.epochs'.
            - Sets the current epoch in the environment variable 'epoch'.
            - Initializes lists for tracking training loss, MAPE, and RMSE.
            - Measures the start time of each epoch and shuffles the training data.
            - Calculates the total number of iterations for the training dataloader and stores it in 'iter_f'.
        """
        no_improvement_iter = 0
        os.environ['epoch'] = str(i)
        os.environ["BEST_MODEL_ITER"] = "0"
        train_loss = []
        train_mape = []
        train_rmse = []
        t1 = time.time()
        dataloader['train_loader'].shuffle()
        total_iters = sum(1 for _ in dataloader['train_loader'].get_iterator())
        os.environ['iter_f'] = str(total_iters - 1)
        for iter, (x, y) in enumerate(dataloader['train_loader'].get_iterator()):
            """
                Trains the model using the training dataloader for each iteration within the epoch.
                - Iterates over the training data, processing batches of input ('x') and output ('y').
                - Transposes the dimensions of 'trainx' and 'trainy' for compatibility with the model.
                - Randomly permutes node indices at specified intervals to create splits for training.
            """
            os.environ['iter'] = str(iter)
            os.environ['PRINT_EVERY'] = str(args.print_every)
            if isinstance(x, np.ndarray):
                trainx = torch.from_numpy(x).to(device, non_blocking=True).float()
                trainy = torch.from_numpy(y).to(device, non_blocking=True).float()
            else:
                trainx = torch.as_tensor(x, device=device)
                trainy = torch.as_tensor(y, device=device)
            trainx = trainx.transpose(1, 3)
            trainy = trainy.transpose(1, 3)

            if iter % args.step_size2 == 0:
                perm = torch.randperm(args.num_nodes, device=device)
            num_sub = int(args.num_nodes/args.num_split)
            for j in range(args.num_split):
                """
                   Trains the model on specified splits of the training data, tracking performance metrics.
                   - Divides the training data into 'num_split' segments based on a randomly permuted order of node indices.
                   - For each split, creates tensor subsets for 'trainx' and 'trainy' based on the selected indices.
                   - Calls the 'train' method of the 'engine' to perform training on the current split.
                   - Collects metrics such as loss, MAPE, and RMSE for tracking performance across splits.
                   - Updates the minimum training loss and saves the model's adjacency configuration if a new minimum is found.
                   """
                if j != args.num_split-1:
                    id = perm[j * num_sub:(j + 1) * num_sub]
                else:
                    id = perm[j * num_sub:]
                tx = trainx[:, :, id, :]
                ty = trainy[:, :, id, :]
                #print(f"trainx shape: {trainx.shape}, trainy shape: {trainy[:, 0, :, :].shape}")
                metrics = engine.train(tx, ty[:,0,:,:],id)
                train_loss.append(metrics[0])
                train_mape.append(metrics[1])
                train_rmse.append(metrics[2])
                if metrics[0] < best_loss_in_iter:
                    best_loss_in_iter = metrics[0]
                    os.environ["BEST_MODEL_ITER"] = str(iter)

            if int(os.environ['iter']) % int(os.environ['PRINT_EVERY']) == 0:
                log = 'Iter: {:03d}, Train Loss: {:.4f}, Train MAPE: {:.4f}, Train RMSE: {:.4f}'
                print(log.format(iter, train_loss[-1], train_mape[-1], train_rmse[-1]),flush=True)
                '''
                To see gradients:
                for name, param in model.named_parameters():
                    if 'in_act_net' in name or 'out_act_net' in name:
                        print(name, param.grad.norm().item() if param.grad is not None else "No grad")
                '''
                if os.environ["WANDB_RUN"] == "true":
                    wandb.log({"train_loss_Iter": train_loss[-1],
                               "train_MAPE_Iter": train_mape[-1],
                               "train_RMSE_Iter": train_rmse[-1]})

            ##### EARLY STOPPING PER ITERATION (based on train_loss) #####
            if best_loss_in_iter < best_train_loss_iter - 1e-4:
                best_train_loss_iter = best_loss_in_iter
                no_improvement_iter = 0
            else:
                no_improvement_iter += 1
                if no_improvement_iter % 50 == 0:
                    print(
                        f"[EarlyStopping-Iter] No improvement in train loss for {no_improvement_iter} iterations")

            if no_improvement_iter >= patience_iter:
                print(f"[EarlyStop-Iter] Stopping early at iteration {iter} due to no improvement in train loss")
                early_stop = True
                break  # Exits the iteration loop, but not the entire training
            #model.save_adj()

        t2 = time.time()
        train_time.append(t2-t1)

        # validation
        valid_loss = []
        valid_mape = []
        valid_rmse = []

        s1 = time.time()
        for iter, (x, y) in enumerate(dataloader['val_loader'].get_iterator()):
            """
                Evaluates the model on the validation dataset, tracking performance metrics.
                - Iterates over the validation data, processing batches of input ('x') and output ('y').
                - Transposes the dimensions of 'testx' and 'testy' for compatibility with the model.
                - Calls the 'eval' method of the 'engine' to compute metrics on the validation data.
                - Collects validation metrics including loss, MAPE, and RMSE for performance tracking.
            """
            if isinstance(x, np.ndarray):
                testx = torch.from_numpy(x).to(device, non_blocking=True).float()
                testy = torch.from_numpy(y).to(device, non_blocking=True).float()
            else:
                testx = torch.as_tensor(x, device=device)
                testy = torch.as_tensor(y, device=device)
            testx = testx.transpose(1, 3)
            testy = testy.transpose(1, 3)

            metrics = engine.eval(testx, testy[:,0,:,:])
            valid_loss.append(metrics[0])
            valid_mape.append(metrics[1])
            valid_rmse.append(metrics[2])

        s2 = time.time()
        log = 'Epoch: {:03d}, Inference Time: {:.4f} secs'
        print(log.format(i,(s2-s1)))
        val_time.append(s2-s1)
        mtrain_loss = np.mean(train_loss)
        mtrain_mape = np.mean(train_mape)
        mtrain_rmse = np.mean(train_rmse)

        mvalid_loss = np.mean(valid_loss)
        mvalid_mape = np.mean(valid_mape)
        mvalid_rmse = np.mean(valid_rmse)
        # Llamar al scheduler con la pérdida de validación promedio de la época
        engine.scheduler.step(mvalid_loss)
        his_loss.append(mvalid_loss)

        log = 'Epoch: {:03d}, Train Loss: {:.4f}, Train MAPE: {:.4f}, Train RMSE: {:.4f}, Valid Loss: {:.4f}, Valid MAPE: {:.4f}, Valid RMSE: {:.4f}, Training Time: {:.4f}/epoch'
        print(log.format(i, mtrain_loss, mtrain_mape, mtrain_rmse, mvalid_loss, mvalid_mape, mvalid_rmse, (t2 - t1)),flush=True)

        if mvalid_loss < minl:
            """
                Checks and updates the best model state based on validation loss.
                - Compares the current validation loss ('mvalid_loss') with the minimum loss recorded ('minl').
                - If the current loss is lower, updates 'minl' and saves the model's state dictionary.
                - Sets an environment variable to indicate the best model state and saves the model's adjacency configuration.
                - Cleans up the environment variable after saving the model.
            """
            minl = mvalid_loss
            best_model_state = engine.model.state_dict()
            # Save final adj
            os.environ["model_best"] = "true"
            model.save_adj()

            # EARLY STOPPING BASADO EN VALIDATION LOSS
            if mvalid_loss < best_val_loss_epoch - 1e-4:
                best_val_loss_epoch = mvalid_loss
                no_improvement_epoch = 0
                print(f"[EarlyStopping-Epoch] New best validation loss: {best_val_loss_epoch:.6f}")
            else:
                no_improvement_epoch += 1
                print(
                    f"[EarlyStopping-Epoch] No improvement in validation loss for {no_improvement_epoch} consecutive epochs")

            if no_improvement_epoch >= patience_epoch:
                print(f"[EarlyStopping-Epoch] Stopping early at epoch {i} due to no improvement in validation loss")
                break

        # Save values of metrics to metadata
        os.environ["TRAIN_LOSS"] = str(mtrain_loss)
        os.environ["TRAIN_RMSE"] = str(mtrain_rmse)
        os.environ["VALIDATION_LOSS"] = str(mvalid_loss)
        os.environ["VALIDATION_RMSE"] = str(mvalid_rmse)

        if os.environ["WANDB_RUN"] == "true":
            wandb.log({"E_Train_loss": mtrain_loss,
                       "E_Train_mape": mtrain_mape,
                       "E_Train_rmse": mtrain_rmse,
                       "E_Valid_loss": mvalid_loss,
                       "E_Valid_mape": mvalid_mape,
                       "E_Valid_rmse": mvalid_rmse,
                       "Infer_Time": np.mean(val_time)
                       })

    ###############  Training completed and start forecasting  ###############
    print("Average Training Time: {:.4f} secs/epoch".format(np.mean(train_time)))
    print("Average Inference Time: {:.4f} secs".format(np.mean(val_time)))
    """
        Handles model saving and loading based on the task specified in the environment variable.
        - If the task is "train":
          - Saves the best model state to a local path and an S3 bucket using 'save_s3_model'.
          - Reloads the saved model state from the local path to ensure consistency.
        - If the task is "test":
          - Loads a pre-trained model from the specified path.
          - Saves the loaded model's state to a local path for backup.
    """
    print("CLIENT:", os.environ.get("CLIENT"))
    print("MODEL_NAME:", os.environ.get("MODEL_NAME"))
    print("DATE_YMD_HMS:", os.environ.get("DATE_YMD_HMS"))
    if os.environ["TASK"] == "train":
        torch.save(best_model_state, f"{os.environ['SAVE_FOLDER_PATH']}/model.pth")
        #save_s3_model(best_model_state, args)
        engine.model.load_state_dict(torch.load(f"{os.environ['SAVE_FOLDER_PATH']}/model.pth"))
    elif os.environ["TASK"] == "test":
        engine.model.load_state_dict(torch.load(f"{os.environ['MODEL_FOLDER_PATH']}/model.pth"))
        torch.save(engine.model.state_dict(), f"{os.environ['SAVE_FOLDER_PATH']}/model.pth")
    elif os.environ["TASK"] == "re-train":
        model_dir = f"/app/models/{os.environ['CLIENT']}/{os.environ['MODEL_NAME']}_{os.environ['DATE_YMD_HMS']}"
        os.makedirs(model_dir, exist_ok=True)
        torch.save(best_model_state, f"{model_dir}/model.pth")
        engine.model.load_state_dict(torch.load(f"{model_dir}/model.pth"))

    bestid = np.argmin(his_loss)
    val_loss_model = his_loss[bestid]
    os.environ["VAL_LOSS_MODEL"] = str(val_loss_model)
    print("Training finished")
    print("The valid loss on best model is", str(round(his_loss[bestid], 4)))

    """
        Generates predictions for the training/validation/test data using the model, handling scaling if required.
        - Transforms the actual target values ('realy') and stores them on the specified device.
        - Iterates over the training/validation/test data and generates predictions using the model's 'pred' function.
        - Handles both "stgnn" and "cognn" models for prediction.
        - Concatenates the predictions from each batch and adjusts the size to match the real target data.
        - If scaling is enabled, applies inverse scaling to the predictions using 'scaler'.
    """
    ##### train data #####
    outputs = []
    realy = torch.Tensor(dataloader['y_train']).to(device)
    realy = realy.transpose(1,3)[:,0,:,:]
    for iter, (x, y) in enumerate(dataloader['train_loader'].get_iterator()):
        testx = torch.from_numpy(x).to(device, non_blocking=True).float()
        testx = testx.transpose(1,3)
        with torch.no_grad():
            if os.environ['MODEL_NAME'] == 'STGNN':
                preds,_ = engine.pred(testx)
            elif os.environ['MODEL_NAME'] == 'COGNN':
                preds = engine.pred(testx)
            preds = preds.transpose(1,3)
        outputs.append(preds)
    yhat = torch.cat(outputs,dim=0)
    yhat = yhat[:realy.size(0),...]
    pred_norm = yhat  # escala del modelo (normalizada si aplica)
    # (opcional) para métricas en original:
    # pred_denorm = scaler.inverse_transform(yhat) if args.scaling_required else yhat
    train_pred = pred_norm.squeeze().cpu().detach().numpy()
    train_label = realy.squeeze().cpu().detach().numpy()

    ##### val data #####
    outputs = []
    realy = torch.Tensor(dataloader['y_val']).to(device)
    realy = realy.transpose(1,3)[:,0,:,:]
    for iter, (x, y) in enumerate(dataloader['val_loader'].get_iterator()):
        testx = torch.from_numpy(x).to(device, non_blocking=True).float()
        testx = testx.transpose(1,3)
        with torch.no_grad():
            if os.environ['MODEL_NAME'] == 'STGNN':
                preds, adp = engine.pred(testx)
            elif os.environ['MODEL_NAME'] == 'COGNN':
                preds = engine.pred(testx)
            preds = preds.transpose(1,3)
        outputs.append(preds)
    yhat = torch.cat(outputs,dim=0)
    yhat = yhat[:realy.size(0),...]
    pred_norm = yhat  # escala del modelo (normalizada si aplica)
    # (opcional) para métricas en original:
    # pred_denorm = scaler.inverse_transform(yhat) if args.scaling_required else yhat
    val_pred = pred_norm.squeeze().cpu().detach().numpy()
    val_label = realy.squeeze().cpu().detach().numpy()

    ##### test data #####
    outputs = []
    realy = torch.Tensor(dataloader['y_test']).to(device)
    print("Shape of really is: ", realy.shape)
    realy = realy.transpose(1, 3)[:, 0, :, :]
    for iter, (x, y) in enumerate(dataloader['test_loader'].get_iterator()):
        testx = torch.from_numpy(x).to(device, non_blocking=True).float()
        testx = testx.transpose(1, 3)
        with torch.no_grad():
            if os.environ['MODEL_NAME'] == 'STGNN':
                preds, adp = engine.pred(testx)
            elif os.environ['MODEL_NAME'] == 'COGNN':
                preds = engine.pred(testx)
            preds = preds.transpose(1, 3)
        outputs.append(preds)
    if os.environ['MODEL_NAME'] == 'STGNN':
        adp = adp.cpu().detach().numpy() # save a copy of learned pairwise correlation graph
    else:
        pass
    yhat = torch.cat(outputs, dim=0)  # WADI: (17408, 1, nodes, 1)
    yhat = yhat[:realy.size(0), ...]  # WADI: (17275, 1, nodes, 1)
    pred_norm = yhat  # escala del modelo (normalizada si aplica)
    # (opcional) para métricas en original:
    # pred_denorm = scaler.inverse_transform(yhat) if args.scaling_required else yhat
    test_pred = pred_norm.squeeze().cpu().detach().numpy()
    test_label = realy.squeeze().cpu().detach().numpy()

    #print("Attention to the following results, test_pred and test_label: ")
    #print(test_pred)
    #print(test_label)

    if os.environ["TASK"] != "re-train" and args.save_result:
        """
            Saves training, validation, and test results to disk if result saving is enabled.
        """
        print("Saving results...")
        os.makedirs(os.path.dirname(f"{args.save}{os.environ['CLIENT']}/{os.environ['sweep_proyect']}"), exist_ok=True)
        os.makedirs(os.path.dirname(f"{args.save}{os.environ['CLIENT']}/{os.environ['sweep_proyect']}/{os.environ['run_name']}"), exist_ok=True)
        # train
        np.save(f"{os.environ['SAVE_FOLDER_PATH']}/train_pred_0.npy", train_pred)
        np.save(f"{os.environ['SAVE_FOLDER_PATH']}/train_label_0.npy", train_label)
        # val
        np.save(f"{os.environ['SAVE_FOLDER_PATH']}/val_pred_0.npy",val_pred)
        np.save(f"{os.environ['SAVE_FOLDER_PATH']}/val_label_0.npy",val_label)
        # test
        np.save(f"{os.environ['SAVE_FOLDER_PATH']}/test_pred_0.npy",test_pred)
        np.save(f"{os.environ['SAVE_FOLDER_PATH']}/test_label_0.npy",test_label)
        if os.environ['MODEL_NAME'] == 'STGNN':
            # ADP - MTCL layer uni-directed graph
            np.save(f"{os.environ['SAVE_FOLDER_PATH']}/ADP_{runid}.npy", adp)

    ############### Anomaly Detection and Diagnosis ###############
    print("==========: Anomaly Detection and Diagnosis :===========", flush=True)
    anomaly_detector = anomaly_dd(train_label, val_label, test_label, train_pred, val_pred, test_pred, args.normalization_window, args.error_batch_size)
    indicator, prediction, val_re = anomaly_detector.scorer(args.pca_compo)
    if os.environ["WANDB_RUN"]=="true":
        wandb.log({"TEST_RMSE": float(os.environ["TEST_RMSE"]),
                   "VAL_RMSE": float(os.environ["VAL_RMSE"]),
                   "VAL_LOSS_MODEL": float(os.environ["VAL_LOSS_MODEL"])})

    # Save the PCA model for later use in inference
    print("Saving PCA model...")
    if os.environ["TASK"] == "test":
        anomaly_detector.save_pca_model(f"{args.save}{os.environ['CLIENT']}/pca_model.pkl")
    elif os.environ["TASK"] == "train":
        anomaly_detector.save_pca_model(f"{os.environ['SAVE_FOLDER_PATH']}/pca_model.pkl")
    elif os.environ["TASK"] == "re-train":
        anomaly_detector.save_pca_model(f"/app/models/{os.environ['CLIENT']}/{os.environ['MODEL_NAME']}_{os.environ['DATE_YMD_HMS']}/pca_model.pkl")

    # Evaluate results (remember we are taking a subset in the labels too)
    with open(f"{os.environ['SAVE_FOLDER_PATH']}/subset_anomaly_labels.txt",'r') as f:
        labels = [int(float(i)) for i in f.read().split(',')]
    # Check labels
    if all(label == 0 for label in labels):
        os.environ['LABEL_0'] = 'true'
    else:
        os.environ['LABEL_0'] = 'false'
        pointwise = pointwise_evaluation(gt_labels=labels,pred_labels=prediction,scoring=indicator)
        early = early_detection_evaluation(labels,indicator,args.delays)

    # Save metadata in local
    """
        Saves model metadata, including configuration and specific thresholds, to a JSON file.
    """
    if os.environ["TASK"] != "re-train":
        metadata_path = f"{os.environ['SAVE_FOLDER_PATH']}/model_metadata.json"
    elif os.environ["TASK"] == "re-train":
        metadata_path = f"/app/models/{os.environ['CLIENT']}/{os.environ['MODEL_NAME']}_{os.environ['DATE_YMD_HMS']}/model_metadata.json"
    else:
        raise ValueError(f"Unexpected TASK value: {os.environ['TASK']}")

    #print("[DEBUG] Saving model_metadata.json to:", metadata_path)
    with open(metadata_path, 'w') as json_file:
        data_dict = vars(args)
        data_dict["threshold"] = float(os.environ['threshold_best'])
        # Format date
        parsed_time = datetime.datetime.strptime(os.environ['DATE_YMD_HMS'], '%YY-%mM-%dD_%Hh-%Mm-%Ss')
        date_format = parsed_time.strftime('%Y-%m-%d %H:%M:%S')
        data_dict["Date"] = date_format
        data_dict["Train loss"] = os.environ["TRAIN_LOSS"]
        data_dict["Train rmse"] = os.environ["TRAIN_RMSE"]
        data_dict["Validation loss"] = os.environ["VALIDATION_LOSS"]
        data_dict["Validation rmse"] = os.environ["VALIDATION_RMSE"]
        if "new_temp" in os.environ:
            data_dict["temp"] = float(os.environ['new_temp'])
        data_dict = make_serializable(data_dict)
        json.dump(data_dict, json_file, indent=4)

    if os.environ['LABEL_0'] == 'false':
        return pointwise, early
    else:
        return 0, 0

def train_sweep():
    """
        Initializes a training sweep for the model using Weights & Biases (WandB).

        This function sets up a WandB run, modifies training arguments, and runs the main
        training process. It collects performance metrics, saves them to a JSON file,
        and updates any existing metrics if applicable.

        Steps:
        1. Initialize WandB for tracking.
        2. Modify training arguments.
        3. Execute the main training routine.
        4. Save metrics to a JSON file, either creating a new file or updating an existing one.

        Attributes:
        ----------
        - args : Namespace
            The command-line arguments for the training process.
        - pointwise : dict
            Metrics obtained from the training process.
        - early : object
            Placeholder for early stopping or additional functionality.
    """
    wandb.init(job_type="sweep")
    # Modify args
    wandb_set_args(args)
    # Run main
    pointwise, early = main(0)

    wandb.finish()
    if os.environ['LABEL_0'] == 'false':
        print("<<<=======================================================>>>")
        print("Model successfully trained and train process upload to WandB.")
        print("<<<=======================================================>>>")
        df_point = pd.DataFrame([pointwise])
        df_metrics_new = df_point.copy()
        df_metrics_new['sweep_name'] = os.environ['sweep_proyect']
        df_metrics_new['run_name'] = os.environ['run_name']
        df_metrics_new.to_json(f"{args.save}{os.environ['CLIENT']}/{os.environ['sweep_proyect']}/metrics.json",indent=4)
        os.environ['metrics_local_path'] = f"{args.save}{os.environ['CLIENT']}/metrics.json"
        if os.path.exists(os.environ['metrics_local_path']):
            df_metrics_old = pd.read_json(os.environ['metrics_local_path'], orient='columns')
            df_metrics_cat = pd.concat([df_metrics_old, df_metrics_new], axis=0, ignore_index=True)
            df_metrics_cat.to_json(os.environ['metrics_local_path'], orient='columns', indent=4)
            print('Metrics saved in path: ' + os.environ['metrics_local_path'])
        else:
            df_metrics_new.to_json(os.environ['metrics_local_path'], orient='columns', indent=4)
            print('Metrics saved in path: ' + os.environ['metrics_local_path'])
    else:
        pass

if __name__ == "__main__":
    """
        Main entry point for the training script.

        This script initializes the environment variables required for the training process,
        sets up the Weights & Biases (WandB) tracking system, and handles the training process
        based on the specified configuration.

        Steps:
        1. Load necessary environment variables (e.g., WandB keys, AWS credentials).
        2. Parse S3 paths and set corresponding environment variables.
        3. Validate the specified model type against a list of allowed models.
        4. Configure WandB sweeps if applicable, or run the training process directly.

        Environment Variables:
        ----------------------
        - WANDB_KEY : str
            The key for accessing WandB.
        - WANDB_RUN : str
            Indicates whether to run a WandB sweep.
        - AWS_ACCESS_KEY_ID : str
            AWS access key ID for accessing resources.
        - AWS_SECRET_ACCESS_KEY : str
            AWS secret access key for accessing resources.
        - data : str, optional
            The path to the dataset, used to determine the client name.
        - MODEL : str
            The model to use for training.
        - sensor_split : str
            Determines if sensor splitting is required.

        Raises:
        -------
        ValueError : If the specified model is not in the allowed list.
    """
    print("==========: Loading environment variables :===========", flush=True)
    wandb_key = os.environ['WANDB_KEY']
    wandb_run = os.environ['WANDB_RUN']
    AWS_ACCESS_KEY_ID = os.environ['AWS_ACCESS_KEY_ID']
    AWS_SECRET_ACCESS_KEY = os.environ['AWS_SECRET_ACCESS_KEY']
    os.environ['MODEL_NAME'] = os.environ['MODEL'].split('-')[0].upper()
    os.environ['DATE_YMD_HMS'] = time.strftime('%YY-%mM-%dD_%Hh-%Mm-%Ss')

    print("Client: {}".format(os.environ['CLIENT']))
    print(f"Model: {os.environ['MODEL_NAME']}")
    print(f"Date: {os.environ['DATE_YMD_HMS']}")
    print(f"data path: {args.data}")

    # store s3 paths
    s3_path_full = (f"s3://airtrace-flowguard/{os.environ['CLIENT']}/Algorithm/{os.environ['MODEL_NAME']}/All-models")
    parts_s3_path = s3_path_full.split('/')
    os.environ['bucket'] = parts_s3_path[2]
    print("Bucket: {}".format(os.environ['bucket']))

    os.environ['f_Algorithm'] = parts_s3_path[4]
    os.environ['f_STGNN'] = parts_s3_path[5]
    os.environ['f_All-models'] = parts_s3_path[6]
    model_list = {"stgnn-topk", "stgnn-gat", "cognn"}
    model_used = os.getenv("MODEL")
    if model_used not in model_list:
        raise ValueError(f"Modelo no válido para MODEL: {model_used}. Los modelos permitidos son: {model_list}")
    os.environ['run_count'] = str(1)

    if os.environ['WANDB_RUN'] == "true":
        print("=================: Start WandB sweep :==================", flush=True)
        overall = []
        early_detect = []
        sweep_config = set_sweep_config()
        if sweep_config["method"] == 'bayes':
            os.environ["method"] = "bayes"
        else:
            os.environ["method"] = "other"
        config_json = load_config_file('/app/config.json')
        sweep_id = wandb.sweep(sweep_config, project=config_json["Project_Name"])
        run_sweep = wandb.agent(sweep_id, project=config_json["Project_Name"], function=train_sweep, count=config_json['run_count'])
        # To save all sweep under the same agent
        #sweep_id = '9r6h9irv'                        # ID of the sweep where you want to upload data
        #proyect_name = 'ESAMUR'    # Proyect name
        #os.environ['RE_TRAIN'] = '1'
        #run_sweep = wandb.agent(sweep_id, project=proyect_name, function=train_sweep, count=5)
        if os.environ['LABEL_0'] == 'false':
            df = pd.read_json(os.environ['metrics_local_path'], orient='columns')
    else:
        print("===========: Load config values for training :============", flush=True)
        overall = []
        early_detect = []
        wandb_set_args(args)
        pointwise, early = main(0)
        overall.append(pointwise)
        early_detect.append(early)
        df = pd.DataFrame(overall)
    if os.environ['LABEL_0'] == 'false':
        #print("<<<=======================================================>>>")
        #subprocess.run(['python', '/app/dataloader/adj_to_ETL.py'])
        #print("Adjacency matrix sent to ETL")
        print("<<<=======================================================>>>")
        mean = dict(df.mean().round(4))
        std = dict(df.std().round(4))

        print('\n\n-----------Overall Detection Results-----------\n\n')
        print('---- AUC result ----')
        table_data = [['Metric:','ROC-AUC','PRC-AUC'],
        ['mean:',mean['roc'],mean['prc']],
        ['std:',std['roc'],std['prc']]]
        for row in table_data:
            print("{: >20} {: >20} {: >20}".format(*row))

        print('---- Best F1 result ----')
        table_data = [['Metric:','Precision','Recall','F1'],
        ['mean:',mean['best_precision'],mean['best_recall'],mean['best_f1']],
        ['std:',std['best_precision'],std['best_recall'],std['best_f1']]]
        for row in table_data:
            print("{: >20} {: >20} {: >20} {: >20}".format(*row))

        print('---- Automatic threshold ----')
        table_data= [['Metric:','Precision','Recall','F1'],
        ['mean:',mean['auto_precision'],mean['auto_recall'],mean['auto_f1']],
        ['std:',std['auto_precision'],std['auto_recall'],std['auto_f1']]]
        for row in table_data:
            print("{: >20} {: >20} {: >20} {: >20}".format(*row))

        if os.environ['WANDB_RUN'] == "false":
            print('\n\n-----------Early Detection Results-----------\n\n')
            num = int(len(args.delays) / 3 + 0.5)
            for i in range(num):
                df = pd.DataFrame(early_detect)
                mean = dict(df.mean().round(4))
                std = dict(df.std().round(4))
                table_data = [['Delay'] + [str(d) for d in args.delays[i * 3:(i + 1) * 3]],
                              ['mean:'] + [str(mean['delay_' + str(d)]) for d in args.delays[i * 3:(i + 1) * 3]],
                              ['std:'] + [str(std['delay_' + str(d)]) for d in args.delays[i * 3:(i + 1) * 3]]]

                for row in table_data:
                    print("{: >20} {: >20} {: >20} {: >20}".format(*row))
    else:
        pass
