import torch
import torch.nn as nn
from pts3d import *
from ops import *
import torchvision.models as models
import functools


class Flatten(nn.Module):
    def forward(self, input):
        return input.view(input.size(0), -1)



class Generator(nn.Module):
    def __init__(self, input_nc = 3, output_nc = 3, ngf=64, norm_layer=nn.BatchNorm2d, use_dropout=False, n_blocks=9, padding_type='zero'):
        assert(n_blocks >= 0)
        super(Generator, self).__init__()
        self.input_nc = input_nc
        self.output_nc = output_nc
        self.ngf = ngf
        norm_layer = nn.BatchNorm2d

        self.audio_extractor = nn.Sequential(
            conv2d(1,32,3,1,1),
            conv2d(32,64,3,2,1),
            conv2d(64,128,3,1,1),
            conv2d(128,256,3,2,1),
            nn.MaxPool2d((1,2),(1,2)),
        )



        if type(norm_layer) == functools.partial:
            use_bias = norm_layer.func == nn.InstanceNorm2d
        else:
            use_bias = norm_layer == nn.InstanceNorm2d

        model = [nn.ReflectionPad2d(3),
                 nn.Conv2d(input_nc, ngf, kernel_size=7, padding=0,
                           bias=use_bias),
                 norm_layer(ngf),
                 nn.ReLU(True)]


        n_downsampling = 2
        for i in range(n_downsampling):
            mult = 2**i
            model += [nn.Conv2d(ngf * mult, ngf * mult * 2, kernel_size=3,
                                stride=2, padding=1, bias=use_bias),
                      norm_layer(ngf * mult * 2),
                      nn.ReLU(True)]

        self.image_encoder = nn.Sequential(*model)


        norm_layer = nn.BatchNorm3d
        self.compress = nn.Sequential(
            nn.Conv3d(ngf * 8, ngf * mult * 2, kernel_size=3,
                                stride=1, padding=1, bias=use_bias),
            norm_layer(ngf * mult * 2),
            nn.ReLU(True)

            )

        model = []

        mult = 2**n_downsampling
        for i in range(n_blocks):
            model += [ResnetBlock(ngf * mult, padding_type=padding_type, norm_layer=norm_layer, use_dropout=use_dropout, use_bias=use_bias)]

        for i in range(n_downsampling):
            mult = 2**(n_downsampling - i)
            model += [nn.ConvTranspose3d(ngf * mult, int(ngf * mult / 2),
                                         kernel_size=(3,3,3), stride=(1,2,2),
                                         padding=(1), output_padding=(0,1,1),
                                         bias=use_bias),
                      norm_layer(int(ngf * mult / 2)),
                      nn.ReLU(True)]

        model += [nn.Conv3d(ngf, output_nc, kernel_size=7, padding=3)]
        model += [nn.Tanh()]

        self.generator = nn.Sequential(*model)





    def forward(self, input, audio):
        image_feature = self.image_encoder(input).unsqueeze(2).repeat(1,1,audio.size(2)/4,1,1)
        audio_feature = self.audio_extractor(audio).unsqueeze(-1).repeat(1,1,1,1,image_feature.size(-1))

        new_input = torch.cat([image_feature,audio_feature],1)
        out = self.compress(new_input)
        out = self.generator(out)

        return out




# Define a resnet block
class ResnetBlock(nn.Module):
    def __init__(self, dim, padding_type, norm_layer, use_dropout, use_bias):
        super(ResnetBlock, self).__init__()
        self.conv_block = self.build_conv_block(dim, padding_type, norm_layer, use_dropout, use_bias)

    def build_conv_block(self, dim, padding_type, norm_layer, use_dropout, use_bias):
        conv_block = []
        p = 0
        if padding_type == 'reflect':
            conv_block += [nn.ReflectionPad3d(1)]
        elif padding_type == 'replicate':
            conv_block += [nn.ReplicationPad3d(1)]
        elif padding_type == 'zero':
            p = (0,1,1)
        else:
            raise NotImplementedError('padding [%s] is not implemented' % padding_type)

        conv_block += [nn.Conv3d(dim, dim, kernel_size=(1,3,3), padding=p, bias=use_bias),
                       norm_layer(dim),
                       nn.ReLU(True)]
        if use_dropout:
            conv_block += [nn.Dropout(0.5)]

        p = 0
        if padding_type == 'reflect':
            conv_block += [nn.ReflectionPad3d(1)]
        elif padding_type == 'replicate':
            conv_block += [nn.ReplicationPad3d(1)]
        elif padding_type == 'zero':
            p = (0,1,1)
        else:
            raise NotImplementedError('padding [%s] is not implemented' % padding_type)
        conv_block += [nn.Conv3d(dim, dim, kernel_size=(1,3,3), padding=p, bias=use_bias),
                       norm_layer(dim)]

        return nn.Sequential(*conv_block)

    def forward(self, x):
        out = x + self.conv_block(x)
        return out