import datetime
import os
import time

import torch

from dl4cv.utils import kl_divergence, time_left
from dl4cv.eval.eval_functions import generate_img_figure_for_tensorboardx
import matplotlib.pyplot as plt
import numpy as np

from tensorboardX import SummaryWriter

class Solver(object):

    def __init__(self):
        self.history = {'train_loss': [],
                        'val_loss': [],
                        'total_kl_divergence': [],
                        'kl_divergence_dim_wise': [],
                        'reconstruction_loss': [],
                        'beta': []
                        }

        self.optim = []
        self.criterion = []
        self.training_time_s = 0
        self.stop_reason = ''
        self.beta = 0
        self.epoch = 0

    def train(
            self,
            model,
            train_config,
            dataset_config,
            tensorboard_path,
            optim=None,
            loss_criterion=torch.nn.MSELoss(),
            num_epochs=10,
            max_train_time_s=None,
            train_loader=None,
            val_loader=None,
            log_after_iters=1,
            save_after_epochs=None,
            save_path='../saves/train',
            device='cpu',
            beta=1,
            beta_decay=1,
            target_var=1.,
            patience=128,
            loss_weighting=False,
            loss_weight_ball=2.,
            log_reconstructed_images=True
    ):

        self.train_config = train_config
        self.dataset_config = dataset_config
        model.to(device)

        if self.epoch == 0:
            self.optim = optim
            self.criterion = loss_criterion
            self.beta = beta

        iter_per_epoch = len(train_loader)
        print("Iterations per epoch: {}".format(iter_per_epoch))

        # Exponentially filtered training loss
        train_loss_avg = 0

        # Path to save model and solver
        save_path = os.path.join(save_path, 'train' + datetime.datetime.now().strftime("%Y%m%d%H%M%S"))

        tensorboard_writer = SummaryWriter(os.path.join(tensorboard_path, 'train' + datetime.datetime.now().strftime("%Y%m%d%H%M%S")),
                                           flush_secs=30)

        # Calculate the total number of minibatches for the training procedure
        n_iters = num_epochs*iter_per_epoch
        i_iter = 0

        best_recon_loss = 1e10
        n_bad_iters = 0

        t_start_training = time.time()

        print('Start training at epoch ' + str(self.epoch))
        t_start = time.time()

        # Do the training here
        for i_epoch in range(num_epochs):
            self.epoch += 1
            print("Starting epoch {}, Beta: {}".format(self.epoch, self.beta))
            t_start_epoch = time.time()

            # Set model to train mode
            model.train()

            for i_iter_in_epoch, batch in enumerate(train_loader):
                t_start_iter = time.time()
                i_iter += 1

                x, y, question, _ = batch

                x = x.to(device)
                y = y.to(device)
                if question is not None:
                    question = question.to(device)

                # If using Loss weighting, create a weighting mask
                if loss_weighting:
                    loss_weight_mask = torch.where(y > 1e-3, y * loss_weight_ball, torch.ones_like(y))

                # Forward pass
                y_pred, latent_stuff = model(x, question)

                # Compute losses
                total_kl_divergence = torch.zeros(1, device=device)
                reconstruction_loss = self.criterion(y_pred, y)

                # When using loss weight, multiply the rec_loss with the weight mask and reduce afterwards
                if loss_weighting:
                    reconstruction_loss = reconstruction_loss * loss_weight_mask
                    reconstruction_loss = reconstruction_loss.mean() / loss_weight_mask.mean()

                # KL-loss if latent_stuff contains mu and logvar
                if len(latent_stuff) == 2:
                    mu, logvar = latent_stuff
                    total_kl_divergence, dim_wise_kld, mean_kld = kl_divergence(mu, logvar, target_var)

                loss = reconstruction_loss + self.beta * total_kl_divergence

                # Backpropagate and update weights
                model.zero_grad()
                loss.backward()
                self.optim.step()

                # Reduce beta
                if reconstruction_loss.item() < best_recon_loss:
                    best_recon_loss = reconstruction_loss.item()
                    n_bad_iters = 0
                else:
                    n_bad_iters += 1

                if n_bad_iters >= patience:
                    self.beta *= beta_decay
                    n_bad_iters = 0

                smooth_window_train = 10
                train_loss_avg = (smooth_window_train-1)/smooth_window_train*train_loss_avg + 1/smooth_window_train*loss.item()

                if log_after_iters is not None and (i_iter % log_after_iters == 0):
                    print("Iteration " + str(i_iter) + "/" + str(n_iters) +
                          "   Reconstruction loss: " + "{0:.6f}".format(reconstruction_loss.item()),
                          "   KL loss: " + "{0:.6f}".format(total_kl_divergence.item()) +
                          "   Train loss: " + "{0:.6f}".format(loss.item()) +
                          "   Avg train loss: " + "{0:.6f}".format(train_loss_avg) +
                          " - Time/iter: " + str(int((time.time()-t_start_iter)*1000)) + "ms")

                    # plot_grad_flow(model.named_parameters())

                self.append_history({'train_loss': loss.item(),
                                     'total_kl_divergence': total_kl_divergence.item(),
                                     'kl_divergence_dim_wise': dim_wise_kld.tolist(),
                                     'reconstruction_loss': reconstruction_loss.item(),
                                     'beta': self.beta     # Save beta every iteration to multiply with kl div
                                     })

                # Add losses to tensorboard
                loss_names = ['kl_loss', 'reconstruction_loss', 'train_loss']
                losses = [total_kl_divergence.item()*self.beta, reconstruction_loss.item(), loss.item()]
                tensorboard_writer.add_scalars('loss', dict(zip(loss_names, losses)), i_iter)

                z_keys = ['z{}'.format(i) for i in range(dim_wise_kld.numel())]
                tensorboard_writer.add_scalars('kl_loss_dim_wise',  dict(zip(z_keys, dim_wise_kld.tolist())), i_iter)

                tensorboard_writer.add_scalar('beta', self.beta, i_iter)

                if log_reconstructed_images and os.getcwd()[:20] != '/home/felix.meissen':
                    f = generate_img_figure_for_tensorboardx(y, y_pred, question)
                    plt.show()  # don't log images on server
                    tensorboard_writer.add_figure('Reconstructed sample', f, i_iter)

            # Validate model
            print("\nValidate model after epoch " + str(self.epoch) + '/' + str(num_epochs))

            # Set model to evaluation mode
            model.eval()

            num_val_batches = 0
            val_loss = 0

            for i, batch in enumerate(val_loader):
                num_val_batches += 1

                x, y, question, _ = batch

                x = x.to(device)
                y = y.to(device)
                if question is not None:
                    question = question.to(device)

                # If using Loss weighting, create a weighting mask
                if loss_weighting:
                    loss_weight_mask = torch.where(y > 1e-3, y * loss_weight_ball, torch.ones_like(y))

                y_pred, latent_stuff = model(x, question)

                current_val_loss = self.criterion(y, y_pred)

                # When using loss weight, multiply the rec_loss with the weight mask and reduce afterwards
                if loss_weighting:
                    current_val_loss = current_val_loss * loss_weight_mask
                    current_val_loss = current_val_loss.mean() / loss_weight_mask.mean()

                val_loss += current_val_loss.item()

            val_loss /= num_val_batches

            self.append_history({'val_loss': val_loss})

            print('Avg Train Loss: ' + "{0:.6f}".format(train_loss_avg) +
                  '   Val loss: ' + "{0:.6f}".format(val_loss) +
                  "   - " + str(int((time.time() - t_start_epoch) * 1000)) + "ms" +
                  "   time left: {}\n".format(time_left(t_start, n_iters, i_iter)))

            # Save model and solver
            if save_after_epochs is not None and (self.epoch % save_after_epochs == 0):
                os.makedirs(save_path, exist_ok=True)
                model.save(save_path + '/model' + str(self.epoch))
                self.training_time_s += time.time() - t_start_training
                self.save(save_path + '/solver' + str(self.epoch))
                model.to(device)

            # Stop if training time is over
            if max_train_time_s is not None and (time.time() - t_start_training > max_train_time_s):
                print("Training time is over.")
                self.stop_reason = "Training time over."
                break

        if self.stop_reason is "":
            self.stop_reason = "Reached number of specified epochs."

        # Save model and solver after training
        os.makedirs(save_path, exist_ok=True)
        model.save(save_path + '/model' + str(self.epoch))
        self.training_time_s += time.time() - t_start_training
        self.save(save_path + '/solver' + str(self.epoch))

        print('FINISH.')

    def save(self, path):
        print('Saving solver... %s\n' % path)
        torch.save({
            'history': self.history,
            'epoch': self.epoch,
            'stop_reason': self.stop_reason,
            'training_time_s': self.training_time_s,
            'criterion': self.criterion,
            'beta': self.beta,
            'optim_state_dict': self.optim.state_dict(),
            'train_config': self.train_config,
            'dataset_config': self.dataset_config
        }, path)

    def load(self, path, device, only_history=False):

        checkpoint = torch.load(path, map_location=device)

        if not only_history:
            self.optim.load_state_dict(checkpoint['optim_state_dict'])
            self.criterion = checkpoint['criterion']

        self.history = checkpoint['history']
        self.epoch = checkpoint['epoch']
        self.beta = checkpoint['beta']
        self.stop_reason = checkpoint['stop_reason']
        self.training_time_s = checkpoint['training_time_s']
        if 'train_config' in checkpoint.keys():
            self.train_config = checkpoint['train_config']
        if 'dataset_config' in checkpoint.keys():
            self.dataset_config = checkpoint['dataset_config']

    def append_history(self, hist_dict):
        for key in hist_dict:
            self.history[key].append(hist_dict[key])

def plot_grad_flow(named_parameters):
    '''Plots the gradients flowing through different layers in the net during training.
    Can be used for checking for possible gradient vanishing / exploding problems.

    Usage: Plug this function in Trainer class after loss.backwards() as
    "plot_grad_flow(self.model.named_parameters())" to visualize the gradient flow'''
    ave_grads = []
    max_grads = []
    layers = []
    for n, p in named_parameters:
        if (p.requires_grad) and ("bias" not in n):
            layers.append(n)
            ave_grads.append(p.grad.abs().mean())
            max_grads.append(p.grad.abs().max())
    plt.bar(np.arange(len(max_grads)), max_grads, alpha=0.1, lw=1, color="c")
    plt.bar(np.arange(len(max_grads)), ave_grads, alpha=0.1, lw=1, color="b")
    plt.hlines(0, 0, len(ave_grads) + 1, lw=2, color="k")
    plt.xticks(range(0, len(ave_grads), 1), layers, rotation="vertical")
    plt.xlim(left=0, right=len(ave_grads))
    plt.ylim(bottom=-0.001, top=0.02)  # zoom in on the lower gradient regions
    plt.xlabel("Layers")
    plt.ylabel("average gradient")
    plt.title("Gradient flow")
    plt.grid(True)
    plt.legend([plt.Line2D([0], [0], color="c", lw=4),
                plt.Line2D([0], [0], color="b", lw=4),
                plt.Line2D([0], [0], color="k", lw=4)], ['max-gradient', 'mean-gradient', 'zero-gradient'])
    plt.show()
