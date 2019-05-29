import matplotlib.pyplot as plt
import numpy as np
import torch
import torchvision.transforms as transforms

from dl4cv.dataset_utils import CustomDataset, CustomDatasetRAM
from torch.utils.data.sampler import SequentialSampler


config = {
    'show_images': True,

    'data_path': '../datasets/ball',  # Path to directory of the image folder
    'len_inp_sequence': 3,
    'len_out_sequence': 3,

    'model_path': '../saves/train20190529141500/model10',

    'batch_size': 1000,
    'num_show_images': 10,              # Number of images to show
}


def eval_model(model, samples):
    plt.interactive(False)

    num_cols = max(config['len_inp_sequence'], config['len_out_sequence'])
    num_rows = 4

    plt.rcParams.update({'font.size': 8})

    for sample in samples:

        x, y, meta = sample

        y_pred, latent_stuff = model(torch.unsqueeze(x, 0))

        if config['show_images']:

            to_pil = transforms.ToPILImage()

            f, axes = plt.subplots(num_rows, num_cols)

            # Plot input sequence
            for i in range(config['len_inp_sequence']):
                axes[0, i].imshow(to_pil(x[i]), cmap='gray')
                # axes[0, i].set_title('frame t{}'.format(-(sequence_length - 1) + i))
                # plt.show()

            for i in range(config['len_out_sequence']):
                # Plot ground truth
                axes[1, i].imshow(to_pil(y[i]), cmap='gray')
                # axes[1, i].set_title('Ground truth t+{}'.format(i + 1 - inp_length))

                # Plot prediction
                axes[2, i].imshow(to_pil(y_pred[0, i]), cmap='gray')
                # axes[2, i].set_title('Prediction t+{}'.format(i + 1 - inp_length))

                # Plot Deviation
                diff = abs(y_pred[0, i] - y[i])
                axes[3, i].imshow(to_pil(diff), cmap='gray')
                # axes[3, i].set_title('Deviation t+{}'.format(i + 1 - inp_length))

            # Remove axis ticks
            for ax in axes.reshape(-1):
                ax.axis('off')

            # Label rows
            labels = {0: 'Input sequence',
                      1: 'Ground truth',
                      2: 'Prediction',
                      3: 'Deviation'}

            for i in range(num_rows):
                plt.sca(axes[i, 0])
                plt.tick_params(labelleft=True)
                axes[i, 0].set_ylabel(labels[i])

            plt.show(block=True)


inp_length = config['len_inp_sequence']
out_length = config['len_out_sequence']
sequence_length = inp_length + out_length

dataset = CustomDatasetRAM(
    config['data_path'],
    transform=transforms.Compose([
        transforms.Grayscale(),
        transforms.ToTensor()
    ]),
    len_inp_sequence=config['len_inp_sequence'],
    len_out_sequence=config['len_out_sequence']
)

data_loader = torch.utils.data.DataLoader(
    dataset=dataset,
    batch_size=config['batch_size']
)

model = torch.load(config['model_path'])

x, y, meta = next(iter(data_loader))
# Pick samples from the batch equidistantly based on "num_show_images"
indices = np.linspace(0, config['batch_size'] - 1, config['num_show_images'], dtype=int).tolist()
samples = [(x[indices[i]], y[indices[i]], meta[indices[i]]) for i in range(len(indices))]

eval_model(model, samples)
