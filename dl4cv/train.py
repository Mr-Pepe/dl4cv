import torch

from torch.utils.data import DataLoader, SequentialSampler, SubsetRandomSampler
from torchvision import transforms

from dl4cv.dataset.utils import CustomDataset
from dl4cv.models.models import VariationalAutoEncoder
from dl4cv.solver import Solver


def train(config):

    """ Add a seed to have reproducible results """

    seed = 456
    torch.manual_seed(seed)

    """ Configure training with or without cuda """

    if config['use_cuda'] and torch.cuda.is_available():
        device = torch.device("cuda")
        torch.cuda.manual_seed(seed)
        kwargs = {'pin_memory': True}
        print("GPU available. Training on {}.".format(device))
    else:
        device = torch.device("cpu")
        torch.set_default_tensor_type('torch.FloatTensor')
        kwargs = {}
        print("No GPU. Training on {}.".format(device))

    """ Load dataset """

    print("Loading dataset with input sequence length {} and output sequence length {}...".format(
        config['len_inp_sequence'], config['len_out_sequence']))

    dataset = CustomDataset(
        config['data_path'],
        transform=transforms.Compose([
            transforms.Grayscale(),
            transforms.ToTensor()
        ]),
        len_inp_sequence=config['len_inp_sequence'],
        len_out_sequence=config['len_out_sequence'],
        load_to_ram=config['load_data_to_ram'],
        question=config['use_question'],
        load_ground_truth=False,
        load_config=True
    )

    if config['batch_size'] > len(dataset):
        raise Exception('Batch size bigger than the dataset.')

    if config['do_overfitting']:
        print("Overfitting on a subset of {} samples".format(config['num_train_overfit']))
        if config['batch_size'] > config['num_train_overfit']:
            raise Exception('Batchsize for overfitting bigger than the number of samples for overfitting.')
        else:
            train_data_sampler = SequentialSampler(range(config['num_train_overfit']))
            val_data_sampler = SequentialSampler(range(config['num_train_overfit']))

    else:
        print("Training on {} samples".format(config['num_train_regular']))
        if config['num_train_regular'] + config['num_val_regular'] > len(dataset):
            raise Exception(
                'Trying to use more samples for training and validation than len(dataset), {} > {}.'.format(
                    config['num_train_regular'] + config['num_val_regular'], len(dataset)
                ))
        else:
            train_data_sampler = SubsetRandomSampler(range(config['num_train_regular']))
            val_data_sampler = SubsetRandomSampler(range(
                config['num_train_regular'],
                config['num_train_regular'] + config['num_val_regular']
            ))

    train_data_loader = torch.utils.data.DataLoader(
        dataset=dataset,
        batch_size=config['batch_size'],
        num_workers=config['num_workers'],
        sampler=train_data_sampler,
        drop_last=True,
        **kwargs
    )
    val_data_loader = torch.utils.data.DataLoader(
        dataset=dataset,
        batch_size=config['batch_size'],
        num_workers=config['num_workers'],
        sampler=val_data_sampler,
        drop_last=True,
        **kwargs
    )

    """ Initialize model and solver """

    if config['continue_training']:
        print("Continuing training with model: {} and solver: {}".format(
            config['model_path'], config['solver_path'])
        )

        model = torch.load(config['model_path'])
        model.to(device)
        solver = Solver()
        solver.optim = torch.optim.Adam(model.parameters(), lr=config['learning_rate'])
        solver.load(config['solver_path'], device=device)
        optimizer = None

    else:
        print("Initializing model...")
        model = VariationalAutoEncoder(
            len_in_sequence=config['len_inp_sequence'],
            len_out_sequence=config['len_out_sequence'],
            z_dim_encoder=config['z_dim_encoder'],
            z_dim_decoder=config['z_dim_decoder'],
            use_physics=config['use_physics']
        )
        solver = Solver()
        optimizer = torch.optim.Adam(model.parameters(), lr=config['learning_rate'])

    """ Perform training """
    solver.train(model=model,
                 train_config=config,
                 dataset_config=dataset.config,
                 tensorboard_path=config['tensorboard_log_dir'],
                 optim=optimizer,
                 num_epochs=config['num_epochs'],
                 max_train_time_s=config['max_train_time_s'],
                 train_loader=train_data_loader,
                 val_loader=val_data_loader,
                 log_after_iters=config['log_interval'],
                 save_after_epochs=config['save_interval'],
                 save_path=config['save_path'],
                 device=device,
                 C_offset=config['C_offset'],
                 C_max=config['C_max'],
                 C_stop_iter=config['C_stop_iter'],
                 gamma=config['gamma'],
                 target_var=config['target_var'],
                 log_reconstructed_images=config['log_reconstructed_images'],
                 beta=config['beta'])
