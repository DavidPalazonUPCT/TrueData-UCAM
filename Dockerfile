# Step 1: Base image with CUDA and PyTorch
FROM nvcr.io/nvidia/pytorch:23.12-py3

# Step 2: Install additional dependencies (if any)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    python3-dev \
    python3-pip \
    python3-setuptools \
    git \
    && rm -rf /var/lib/apt/lists/*

RUN pip install jupyter
RUN pip install wandb
RUN pip3 install boto3

# For CoGNN
RUN pip install torch==2.0.0 torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
RUN pip install torch_scatter torch_sparse torch_cluster torch_spline_conv -f https://data.pyg.org/whl/torch-2.0.0+cu118.html
RUN pip install torch-geometric==2.3.0
RUN pip install torchmetrics ogb rdkit matplotlib

COPY ./src /app

ENTRYPOINT ["python", "/app/run.py"]
