import csv
import datetime
import time

import numpy as np
import torch


def kl_divergence(mu, logvar):
    # Taken from https://github.com/1Konny/Beta-VAE/blob/master/solver.py
    batch_size = mu.size(0)
    assert batch_size != 0
    if mu.data.ndimension() == 4:
        mu = mu.view(mu.size(0), mu.size(1))
    if logvar.data.ndimension() == 4:
        logvar = logvar.view(logvar.size(0), logvar.size(1))

    klds = -0.5*(1 + logvar - mu.pow(2) - logvar.exp())
    total_kld = klds.sum(1).mean(0, True)
    dimension_wise_kld = klds.mean(0)
    mean_kld = klds.mean(1).mean(0, True)

    return total_kld, dimension_wise_kld, mean_kld


def reparametrize(mu, logvar):
    # Taken from https://github.com/1Konny/Beta-VAE/blob/master/model.py
    std = logvar.div(2).exp()
    eps = torch.autograd.Variable(std.data.new(std.size()).normal_())
    return mu + std*eps


def save_csv(data, path):
    with open(path, 'w') as f:
        writer = csv.writer(f, delimiter='|')
        writer.writerow(data)


def read_csv(path):
    return np.genfromtxt(path, dtype=np.float, delimiter='|', skip_header=0)


def time_left(t_start, n_iters, i_iter):
    iters_left = n_iters - i_iter
    time_per_iter = (time.time() - t_start) / i_iter
    time_left = time_per_iter * iters_left
    time_left = datetime.datetime.fromtimestamp(time_left)
    return time_left.strftime("%H:%M:%S")