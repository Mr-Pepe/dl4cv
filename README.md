# Learning Interpretable Physical Variables from Image Sequences

This repository contains code to train Autoencoders for learning disentangled latent representations
of single images or image sequences in an unsupervised manner. It also contains code to generate a synthetic dataset
for this purpose. Evaluation functions give qualitative and quantitative feedback on the quality of 
disentanglement.


## Walks over latent variables

A sample of 2000 sequences was used to calculate the latent encoding for the three architectures.
While holding five of the six variables constant at the mean of the observed values for one model, one latent 
variable is sampled between its observed minimum and maximum value. This shows the influence of 
one latent variable on the generated output image.


### Question Autoencoder

![Alt text](dl4cv/final_runs/gifs/question_AE.gif) 

### Beta VAE

![Alt text](dl4cv/final_runs/gifs/beta_vae.gif) 


### Annealed VAE

![Alt text](dl4cv/final_runs/gifs/annealed_VAE.gif)
