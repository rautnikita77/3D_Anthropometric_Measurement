import os
import torch
from pytorch3d.io import load_obj, save_obj, load_objs_as_meshes
from pytorch3d.structures import Meshes
from pytorch3d.utils import ico_sphere
from pytorch3d.ops import sample_points_from_meshes
from pytorch3d.loss import (
    chamfer_distance,
    mesh_edge_loss,
    mesh_laplacian_smoothing,
    mesh_normal_consistency,
)
import numpy as np
from model import Generator, Discriminator, ContrastiveLoss
import cv2
from utils import project_mesh_silhouette, Metadata
from NOMO import Nomo
from torch.utils.data import DataLoader
from tqdm import tqdm
import random
import matplotlib.pyplot as plt
import pickle


# batch_size = 1
# epochs = 50
# d_lr = 1e-2
# g_lr = 1e-2
# beta = 0.9
# inp_feature = 512*512
# device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
# smpl_mesh_path = "Test/smpl_pytorch/human.obj"
# path = "NOMO_preprocess/data"
# device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# def train_discriminator(d, c, projection, real, fake, optimizer):
#     output1, output2 = d(projection, real)
#     output3, output4 = d(projection, fake)
#     loss_contrastive_pos = c(output1, output2, 0)
#     loss_contrastive_neg = c(output3, output4, 1)
#     loss_contrastive = loss_contrastive_neg + loss_contrastive_pos
#     print('Test Loss =  {}'.format(loss_contrastive))
#     loss_contrastive.backward()
#     optimizer.step()
load = True
load_epoch = 39


if __name__ == "__main__":
    meta = Metadata()
    mesh_male = load_objs_as_meshes([os.path.join(meta.path, 'male.obj')], device=meta.device, load_textures=False)
    mesh_female = load_objs_as_meshes([os.path.join(meta.path, 'female.obj')], device=meta.device, load_textures=False)
    mesh = {'male': mesh_male, 'female': mesh_female}

    discriminator = Discriminator()
    # discriminator.load_state_dict(torch.load(os.path.join(meta.model_path, 'discriminator_21')))
    discriminator = discriminator.to(meta.device)
    for param in discriminator.parameters():
        param.requires_grad = False

    print('loading data....')
    transformed_dataset = Nomo(folder=meta.path)
    dataloader = DataLoader(transformed_dataset, batch_size=meta.batch_size, shuffle=False)
    print('done')

    if load:
        deform_verts = pickle.load(open(os.path.join(meta.model_path, "deform_{}".format(str(load_epoch))), "rb"))
        discriminator.load_state_dict(torch.load(os.path.join(meta.model_path, "discriminator_{}".format(str(load_epoch)))))
    else:
        deform_verts = [torch.full(mesh['male'][0].verts_packed().shape, 0.0,
                               device=meta.device, requires_grad=True) for _ in range(len(dataloader))]

    criterion = ContrastiveLoss().to(meta.device)
    optimizer = torch.optim.Adam(list(discriminator.parameters()) + deform_verts, lr=meta.d_lr)

    for epoch in tqdm(range(meta.epochs)):
        epoch_loss = 0
        for i, sample in enumerate(dataloader):
            for n, angle in enumerate([0, 90, 180, 270]):

                optimizer.zero_grad()
                new_mesh = mesh[sample['gender'][0]].offset_verts(deform_verts[i])
                projection = project_mesh_silhouette(new_mesh, angle)
                proj_img = projection.clone()
                # plt.imshow(proj_img.squeeze().detach().cpu().numpy())
                # plt.title('Epoch {} Angle {} Gender {}'.format(str(epoch), str(angle), sample['gender'][0]))
                # plt.show()
                real_angle = angle + random.randint(-5, 5)
                real = project_mesh_silhouette(new_mesh, real_angle)
                fake = sample['images'][0][n].unsqueeze(0).unsqueeze(0).to(meta.device)
                output1, output2 = discriminator(projection, real)
                loss_contrastive_pos = criterion(output1, output2, 0)
                output3, output4 = discriminator(projection, fake)
                loss_contrastive_neg = criterion(output3, output4, 1)
                loss_contrastive = loss_contrastive_neg + loss_contrastive_pos
                # if n == 3:
                #     loss_contrastive.backward()
                # else:
                #     loss_contrastive.backward(retain_graph=True)
                loss_contrastive.backward()
                optimizer.step()

                epoch_loss = loss_contrastive.detach()
                torch.cuda.empty_cache()
        if (epoch+1) % 10 == 0:
            pickle.dump(deform_verts, open("models/deform_{}".format(str(epoch)), "wb"))
            torch.save(discriminator.state_dict(), 'models/discriminator_{}'.format(str(epoch)))
        print("Epoch number {}\n Current loss {}\n".format(epoch, epoch_loss))




