import torch.nn.functional
from functools import partial
from CBaseNetworks import *
import torch.nn.functional as F
import bra_legacy
from timm.models.layers import DropPath, to_2tuple, trunc_normal_
import math
import Mobilev2_for_single
class SEM(nn.Module):
    def __init__(self,in_chan):
        super(SEM,self).__init__()
        self.conv3 = nn.Conv2d(in_chan//4, in_chan, 3,1,1)
        self.conv1 = ConvBNReLU(in_chan,in_chan//4,kernel_size=1)
        self.conv2 = ConvBNReLU(in_chan,in_chan//4,kernel_size=1)
        self.bn3 = nn.BatchNorm2d(in_chan)
        self.relu1=nn.ReLU()
    def _init_weights(self, m):
        if isinstance(m, nn.Linear):
            trunc_normal_(m.weight, std=.02)
            if isinstance(m, nn.Linear) and m.bias is not None:
                nn.init.constant_(m.bias, 0)
        elif isinstance(m, nn.LayerNorm):
            nn.init.constant_(m.bias, 0)
            nn.init.constant_(m.weight, 1.0)
        elif isinstance(m, nn.Conv2d):
            fan_out = m.kernel_size[0] * m.kernel_size[1] * m.out_channels
            fan_out //= m.groups
            m.weight.data.normal_(0, math.sqrt(2.0 / fan_out))
            if m.bias is not None:
                m.bias.data.zero_()

    def forward(self,x1,x2):
        x1_ori=x1
        x2_ori=x2
        x1=self.conv1(x1)
        x2=self.conv2(x2)
        mul=x1*x2
        mul=self.conv3(mul)
        mul=self.bn3(mul)
        out=torch.cat([x1_ori+mul,mul,x2_ori+mul],1)
        out=self.relu1(out)
        return out

class make_sobel(nn.Module):
    def __init__(self,in_chan):
        super(make_sobel,self).__init__()
        self.in_chan = in_chan
        self.edge_diff_conv3 = nn.Conv2d(1, 1, 3, padding=1)
    def forward(self,x):
        sobel_1 = torch.tensor([[0,0,0,0,0],
                                    [-1,-2,-4,-2,-1],
                                    [0,0,0,0,0],
                                    [1,2,4,2,1],
                                    [0,0,0,0,0]], dtype=torch.float32).cuda()

        sobel_2 = torch.tensor([[0, 0, 0, -1, 0],
                                    [0, -2, -4, 0, 1],
                                    [0, -4, 0, 4, 0],
                                    [-1, 0, 4, 2, 0],
                                    [0, 1, 0, 0, 0]],dtype=torch.float32).cuda()

        sobel_3 = torch.tensor([[0, -1, 0, 1, 0],
                                    [0, -2, 0, 2, 0],
                                    [0, -4, 0, 4, 0],
                                    [0, -2, 0, 2, 0],
                                    [0, -1, 0, 1, 0]],dtype=torch.float32).cuda()

        sobel_4 = torch.tensor([[0, 1, 0, 0, 0],
                                    [-1, 0, 4, 2, 0],
                                    [0, -4, 0, 4, 0],
                                    [0, -2, -4, 0, 1],
                                    [0, 0, 0, -1, 0]],dtype=torch.float32).cuda()
        sobel_1 = sobel_1.repeat(1, self.in_chan, 1, 1)
        sobel_2 = sobel_2.repeat(1, self.in_chan, 1, 1)
        sobel_3 = sobel_3.repeat(1, self.in_chan, 1, 1)
        sobel_4 = sobel_4.repeat(1, self.in_chan, 1, 1)

        x1_edge_1 = torch.nn.functional.conv2d(x, sobel_1,padding=2,stride=1)
        x1_edge_2 = torch.nn.functional.conv2d(x, sobel_2, padding=2, stride=1)
        x1_edge_3 = torch.nn.functional.conv2d(x, sobel_3, padding=2, stride=1)
        x1_edge_4 = torch.nn.functional.conv2d(x, sobel_4, padding=2, stride=1)
        x1_edge = torch.square(x1_edge_1) +torch.square(x1_edge_2)+torch.square(x1_edge_3)+torch.square(x1_edge_4)
        x1_edge=torch.sqrt(x1_edge)
        edge_diff = abs(self.edge_diff_conv3(x1_edge))
        return  edge_diff

class MS_CAM(nn.Module):
    def __init__(self, channels=64, r=4):
        super(MS_CAM, self).__init__()
        inter_channels = int(channels // r)

        self.local_att = nn.Sequential(
            nn.Conv2d(channels, inter_channels, kernel_size=1, stride=1, padding=0),
            nn.BatchNorm2d(inter_channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(inter_channels, channels, kernel_size=1, stride=1, padding=0),
            nn.BatchNorm2d(channels),
        )

        self.global_att = nn.Sequential(
            nn.AdaptiveAvgPool2d(1),
            nn.Conv2d(channels, inter_channels, kernel_size=1, stride=1, padding=0),
            nn.BatchNorm2d(inter_channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(inter_channels, channels, kernel_size=1, stride=1, padding=0),
            nn.BatchNorm2d(channels),
        )

        self.sigmoid = nn.Sigmoid()

    def forward(self, x):
        xl = self.local_att(x)
        xg = self.global_att(x)
        xlg = xl + xg
        wei = self.sigmoid(xlg)
        return wei
class AFF(nn.Module):
    def __init__(self, channels=64, r=4):
        super(AFF, self).__init__()
        inter_channels = int(channels // r)

        self.local_att = nn.Sequential(
            nn.Conv2d(channels, inter_channels, kernel_size=1, stride=1, padding=0),
            nn.BatchNorm2d(inter_channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(inter_channels, channels, kernel_size=1, stride=1, padding=0),
            nn.BatchNorm2d(channels),
        )

        self.global_att = nn.Sequential(
            nn.AdaptiveAvgPool2d(1),
            nn.Conv2d(channels, inter_channels, kernel_size=1, stride=1, padding=0),
            nn.BatchNorm2d(inter_channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(inter_channels, channels, kernel_size=1, stride=1, padding=0),
            nn.BatchNorm2d(channels),
        )

        self.sigmoid = nn.Sigmoid()

    def forward(self, x, residual):
        xa = x + residual
        xl = self.local_att(xa)
        xg = self.global_att(xa)
        xlg = xl + xg
        wei = self.sigmoid(xlg)
        xo = 2 * x * wei + 2 * residual * (1 - wei)
        return xo

class OverlapPatchEmbed(nn.Module):


    def __init__(self, img_size=224, patch_size=7, stride=4, in_chans=3, embed_dim=768):
        super().__init__()
        img_size = to_2tuple(img_size)
        patch_size = to_2tuple(patch_size)
        self.img_size = img_size
        self.patch_size = patch_size
        self.H, self.W = img_size[0] // patch_size[0], img_size[1] // patch_size[1]
        self.num_patches = self.H * self.W
        self.proj = nn.Conv2d(in_chans, embed_dim, kernel_size=patch_size, stride=stride,
                              padding=(patch_size[0] // 2, patch_size[1] // 2))
        self.norm = nn.LayerNorm(embed_dim)
        self.conv_dw = dw_conv2d_br(embed_dim, embed_dim)
        self.aff=AFF(embed_dim)


    def _init_weights(self, m):
        if isinstance(m, nn.Linear):
            trunc_normal_(m.weight, std=.02)
            if isinstance(m, nn.Linear) and m.bias is not None:
                nn.init.constant_(m.bias, 0)
        elif isinstance(m, nn.LayerNorm):
            nn.init.constant_(m.bias, 0)
            nn.init.constant_(m.weight, 1.0)
        elif isinstance(m, nn.Conv2d):
            fan_out = m.kernel_size[0] * m.kernel_size[1] * m.out_channels
            fan_out //= m.groups
            m.weight.data.normal_(0, math.sqrt(2.0 / fan_out))
            if m.bias is not None:
                m.bias.data.zero_()

    def forward(self, x,diff_am):
        diff_am=diff_am.repeat(1,2,1,1)
        x = self.proj(x)
        _, _, H, W = x.shape
        x2 = x * diff_am
        x2 = self.conv_dw(x2)
        x = self.aff(x, x2)
        x = x.flatten(2).transpose(1, 2)
        x = self.norm(x)
        return x, H, W

def resize(input, size=None, scale_factor=None, mode='nearest', align_corners=None, warning=True):
    if warning:
        if size is not None and align_corners:
            input_h, input_w = tuple(int(x) for x in input.shape[2:])
            output_h, output_w = tuple(int(x) for x in size)
            if output_h > input_h or output_w > output_h:
                if ((output_h > 1 and output_w > 1 and input_h > 1
                     and input_w > 1) and (output_h - 1) % (input_h - 1)
                        and (output_w - 1) % (input_w - 1)):
                    warnings.warn(
                        f'When align_corners={align_corners}, '
                        'the output would more aligned if '
                        f'input size {(input_h, input_w)} is `x+1` and '
                        f'out size {(output_h, output_w)} is `nx+1`')
    return F.interpolate(input, size, scale_factor, mode, align_corners)

class Mlp(nn.Module):
    def __init__(self, in_features, hidden_features=None, out_features=None, act_layer=nn.GELU, drop=0.):
        super().__init__()
        out_features = out_features or in_features
        hidden_features = hidden_features or in_features
        self.fc1 = nn.Linear(in_features, hidden_features)
        self.dwconv = DWConv(hidden_features)
        self.act = act_layer()
        self.fc2 = nn.Linear(hidden_features, out_features)
        self.drop = nn.Dropout(drop)
        self.apply(self._init_weights)

    def _init_weights(self, m):
        if isinstance(m, nn.Linear):
            trunc_normal_(m.weight, std=.02)
            if isinstance(m, nn.Linear) and m.bias is not None:
                nn.init.constant_(m.bias, 0)
        elif isinstance(m, nn.LayerNorm):
            nn.init.constant_(m.bias, 0)
            nn.init.constant_(m.weight, 1.0)
        elif isinstance(m, nn.Conv2d):
            fan_out = m.kernel_size[0] * m.kernel_size[1] * m.out_channels
            fan_out //= m.groups
            m.weight.data.normal_(0, math.sqrt(2.0 / fan_out))
            if m.bias is not None:
                m.bias.data.zero_()

    def forward(self, x, H, W):
        x = self.fc1(x)
        x = self.dwconv(x, H, W)
        x = self.act(x)
        x = self.drop(x)
        x = self.fc2(x)
        x = self.drop(x)
        return x

class Attention(nn.Module):
    def __init__(self, dim, num_heads=8, qkv_bias=False, qk_scale=None, attn_drop=0., proj_drop=0., sr_ratio=1):
        super().__init__()
        assert dim % num_heads == 0, f"dim {dim} should be divided by num_heads {num_heads}."
        self.dim = dim
        self.num_heads = num_heads
        head_dim = dim // num_heads
        self.scale = qk_scale or head_dim ** -0.5
        self.q = nn.Linear(dim, dim, bias=qkv_bias)
        self.kv = nn.Linear(dim, dim * 2, bias=qkv_bias)
        self.attn_drop = nn.Dropout(attn_drop)
        self.proj = nn.Linear(dim, dim)
        self.proj_drop = nn.Dropout(proj_drop)
        self.sr_ratio = sr_ratio
        if sr_ratio > 1:
            self.sr = nn.Conv2d(dim, dim, kernel_size=sr_ratio, stride=sr_ratio)
            self.norm = nn.LayerNorm(dim)

        self.apply(self._init_weights)

    def _init_weights(self, m):
        if isinstance(m, nn.Linear):
            trunc_normal_(m.weight, std=.02)
            if isinstance(m, nn.Linear) and m.bias is not None:
                nn.init.constant_(m.bias, 0)
        elif isinstance(m, nn.LayerNorm):
            nn.init.constant_(m.bias, 0)
            nn.init.constant_(m.weight, 1.0)
        elif isinstance(m, nn.Conv2d):
            fan_out = m.kernel_size[0] * m.kernel_size[1] * m.out_channels
            fan_out //= m.groups
            m.weight.data.normal_(0, math.sqrt(2.0 / fan_out))
            if m.bias is not None:
                m.bias.data.zero_()

    def forward(self, x, H, W):
        B, N, C = x.shape
        q = self.q(x).reshape(B, N, self.num_heads, C // self.num_heads).permute(0, 2, 1, 3)
        if self.sr_ratio > 1:
            x_ = x.permute(0, 2, 1).reshape(B, C, H, W)
            x_ = self.sr(x_).reshape(B, C, -1).permute(0, 2, 1)
            x_ = self.norm(x_)
            kv = self.kv(x_).reshape(B, -1, 2, self.num_heads, C // self.num_heads).permute(2, 0, 3, 1, 4)
        else:
            kv = self.kv(x).reshape(B, -1, 2, self.num_heads, C // self.num_heads).permute(2, 0, 3, 1, 4)
        k, v = kv[0], kv[1]
        attn = (q @ k.transpose(-2, -1)) * self.scale
        attn = attn.softmax(dim=-1)
        attn = self.attn_drop(attn)
        x = (attn @ v).transpose(1, 2).reshape(B, N, C)
        x = self.proj(x)
        x = self.proj_drop(x)
        return x

class Block(nn.Module):

    def __init__(self, dim, num_heads, mlp_ratio=4., qkv_bias=False, qk_scale=None, drop=0., attn_drop=0.,
                 drop_path=0., act_layer=nn.GELU, norm_layer=nn.LayerNorm, sr_ratio=1):
        super().__init__()
        self.norm1 = norm_layer(dim)
        self.attn = Attention(
            dim,
            num_heads=num_heads, qkv_bias=qkv_bias, qk_scale=qk_scale,
            attn_drop=attn_drop, proj_drop=drop, sr_ratio=sr_ratio)
        self.drop_path = DropPath(drop_path) if drop_path > 0. else nn.Identity()
        self.norm2 = norm_layer(dim)
        mlp_hidden_dim = int(dim * mlp_ratio)
        self.mlp = Mlp(in_features=dim, hidden_features=mlp_hidden_dim, act_layer=act_layer, drop=drop)
        self.apply(self._init_weights)

    def _init_weights(self, m):
        if isinstance(m, nn.Linear):
            trunc_normal_(m.weight, std=.02)
            if isinstance(m, nn.Linear) and m.bias is not None:
                nn.init.constant_(m.bias, 0)
        elif isinstance(m, nn.LayerNorm):
            nn.init.constant_(m.bias, 0)
            nn.init.constant_(m.weight, 1.0)
        elif isinstance(m, nn.Conv2d):
            fan_out = m.kernel_size[0] * m.kernel_size[1] * m.out_channels
            fan_out //= m.groups
            m.weight.data.normal_(0, math.sqrt(2.0 / fan_out))
            if m.bias is not None:
                m.bias.data.zero_()

    def forward(self, x, H, W):
        x = x + self.drop_path(self.attn(self.norm1(x), H, W))
        x = x + self.drop_path(self.mlp(self.norm2(x), H, W))
        return x
class DEM(nn.Module):

    def __init__(self, dim, num_heads, topk,mlp_ratio=4., qkv_bias=False, qk_scale=None, drop=0., attn_drop=0.,
                 drop_path=0., act_layer=nn.GELU, norm_layer=nn.LayerNorm, sr_ratio=1):
        super().__init__()
        self.norm1 = norm_layer(dim)
        self.drop_path = DropPath(drop_path) if drop_path > 0. else nn.Identity()
        self.norm2 = norm_layer(dim)
        mlp_hidden_dim = int(dim * mlp_ratio)
        self.topk=topk
        if topk>0:
            self.cross_attn=bra_legacy.BiLevelRoutingAttention(dim,num_heads=num_heads,n_win=8,qk_dim=dim,kv_per_win=-1,topk=topk)
            self.mlp_2 = Mlp(in_features=dim, hidden_features=mlp_hidden_dim, act_layer=act_layer, drop=drop)
        elif topk<0:
            self.attn = Attention(dim,num_heads=num_heads, qkv_bias=qkv_bias, qk_scale=qk_scale,
                attn_drop=attn_drop, proj_drop=drop, sr_ratio=sr_ratio)
            self.mlp = Mlp(in_features=dim, hidden_features=mlp_hidden_dim, act_layer=act_layer, drop=drop)
        self.norm3 = norm_layer(dim)
        self.norm4 = norm_layer(dim)
        self.apply(self._init_weights)
    def _init_weights(self, m):
        if isinstance(m, nn.Linear):
            trunc_normal_(m.weight, std=.02)
            if isinstance(m, nn.Linear) and m.bias is not None:
                nn.init.constant_(m.bias, 0)
        elif isinstance(m, nn.LayerNorm):
            nn.init.constant_(m.bias, 0)
            nn.init.constant_(m.weight, 1.0)
        elif isinstance(m, nn.Conv2d):
            fan_out = m.kernel_size[0] * m.kernel_size[1] * m.out_channels
            fan_out //= m.groups
            m.weight.data.normal_(0, math.sqrt(2.0 / fan_out))
            if m.bias is not None:
                m.bias.data.zero_()

    def forward(self, x1,x2, H, W):
        B,_,C=x1.shape
        if self.topk>0:
            x1 = x1.reshape(B, H, W, C)
            x2 = x2.reshape(B, H, W, C)
            x1_cross = x1 + self.drop_path(self.cross_attn(self.norm1(x1-x2), self.norm3(x1)))
            x1_cross=x1_cross.reshape(B, H*W, C)
            x1_cross = x1_cross + self.drop_path(self.mlp_2(self.norm4(x1_cross), H, W))
            x2_cross = x2 + self.drop_path(self.cross_attn(self.norm2(x2-x1), self.norm3(x2)))
            x2_cross = x2_cross.reshape(B, H * W, C)
            x2_cross = x2_cross + self.drop_path(self.mlp_2(self.norm4(x2_cross), H, W))
        elif self.topk<0:
            x1 = x1 + self.drop_path(self.attn(self.norm1(x1), H, W))
            x1_cross = x1 + self.drop_path(self.mlp(self.norm2(x1), H, W))
            x2 = x2 + self.drop_path(self.attn(self.norm1(x2), H, W))
            x2_cross = x2 + self.drop_path(self.mlp(self.norm2(x2), H, W))
        elif self.topk==0:
            x1_cross=x1
            x2_cross=x2
        return x1_cross,x2_cross

class DWConv(nn.Module):
    def __init__(self, dim=768):
        super(DWConv, self).__init__()
        self.dwconv = nn.Conv2d(dim, dim, 3, 1, 1, bias=True, groups=dim)
    def forward(self, x, H, W):
        B, N, C = x.shape
        x = x.transpose(1, 2).view(B, C, H, W)
        x = self.dwconv(x)
        x = x.flatten(2).transpose(1, 2)
        return x

# Transformer Decoder
class MLP(nn.Module):

    def __init__(self, input_dim=2048, embed_dim=768):
        super().__init__()
        self.proj = nn.Linear(input_dim, embed_dim)

    def forward(self, x):
        x = x.flatten(2).transpose(1, 2)
        x = self.proj(x)
        return x

def conv_diff(in_channels, out_channels):
    return nn.Sequential(
        nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=1),
        nn.ReLU(),
        nn.BatchNorm2d(out_channels),
        nn.Conv2d(out_channels, out_channels, kernel_size=3, padding=1),
        nn.ReLU()
    )

def make_prediction(in_channels, out_channels):
    return nn.Sequential(
        nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=1),
        nn.ReLU(),
        nn.BatchNorm2d(out_channels),
        nn.Conv2d(out_channels, out_channels, kernel_size=3, padding=1)
    )

def dw_conv2d_br(in_channels, out_channels):
    return nn.Sequential(
        nn.Conv2d(in_channels, in_channels, kernel_size=3, stride=1, padding=1,groups=in_channels),
        nn.PReLU(),
        nn.BatchNorm2d(in_channels),
        nn.Dropout(p=0.6),
    )

class ConvBNReLU(nn.Sequential):
    def __init__(self, in_planes, out_planes, kernel_size=3, stride=1, groups=1, dilation=1):
        padding = (kernel_size - 1) // 2
        if dilation != 1:
            padding = dilation
        super(ConvBNReLU, self).__init__(
            nn.Conv2d(in_planes, out_planes, kernel_size, stride, padding, groups=groups, dilation=dilation,
                      bias=False),
            nn.BatchNorm2d(out_planes),
            nn.ReLU6(inplace=True)
        )

class ChannelAttention(nn.Module):
    def __init__(self, in_channels, ratio=8):
        super(ChannelAttention, self).__init__()
        self.avg_pool = nn.AdaptiveAvgPool2d(1)
        self.max_pool = nn.AdaptiveMaxPool2d(1)
        self.fc1 = nn.Conv2d(in_channels, in_channels // ratio, 1, bias=False)
        self.relu1 = nn.ReLU()
        self.fc2 = nn.Conv2d(in_channels // ratio, in_channels, 1, bias=False)
        self.sigmod = nn.Sigmoid()

    def forward(self, x):
        avg_out = self.fc2(self.relu1(self.fc1(self.avg_pool(x))))
        max_out = self.fc2(self.relu1(self.fc1(self.max_pool(x))))
        out = avg_out + max_out
        return self.sigmod(out)

class SpatialAttention(nn.Module):
    def __init__(self):
        super(SpatialAttention, self).__init__()
        self.conv1 = nn.Conv2d(2, 1, 7, padding=3, bias=False)
        self.sigmoid = nn.Sigmoid()

    def forward(self, x):
        avg_out = torch.mean(x, dim=1, keepdim=True)
        max_out = torch.max(x, dim=1, keepdim=True, out=None)[0]
        x = torch.cat([avg_out, max_out], dim=1)
        x = self.conv1(x)
        return self.sigmoid(x)

class conv_first(nn.Module):
    def __init__(self,in_channel):
        super(conv_first, self).__init__()
        self.conv_1=ConvBNReLU(in_planes=in_channel,out_planes=16)
    def forward(self, x):
        x1=self.conv_1(x)
        return x1

class ASPPConv(nn.Sequential):
    def __init__(self, in_channels, out_channels, dilation):
        modules = [
            nn.Conv2d(in_channels, out_channels, 3, padding=dilation, dilation=dilation, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU()
        ]
        super(ASPPConv, self).__init__(*modules)

class ASPP(nn.Module):
    def __init__(self, in_channels,out_channels, atrous_rates):
        super(ASPP, self).__init__()
        modules = []
        modules.append(nn.Sequential(
            nn.Conv2d(in_channels, out_channels, 1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU()))
        for rate in atrous_rates:
            modules.append(ASPPConv(in_channels, out_channels, rate))
        self.convs = nn.ModuleList(modules)
        self.project = nn.Sequential(
            nn.Conv2d(len(self.convs) * out_channels, out_channels, 1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(),
            nn.Dropout(0.5))
    def forward(self, x):
        res_1 = []
        for conv in self.convs:
            res_1.append(conv(x))
        res = torch.cat(res_1, dim=1)
        return self.project(res)
class abs_nam(nn.Module):
    def __init__(self, in_d=None, out_d=64):
        super(abs_nam, self).__init__()
        if in_d is None:
            in_d = [16, 24, 32, 96, 320]
        self.in_d = in_d
        self.mid_d = out_d // 2
        self.out_d = out_d
        self.aspp_s1=ASPP(in_channels=self.mid_d*2,out_channels=out_d,atrous_rates=[1,3,5,7])
        self.aspp_s2 = ASPP(in_channels=self.mid_d * 2, out_channels=out_d, atrous_rates=[1, 3, 5, 7])
        self.aspp_s3 = ASPP(in_channels=self.mid_d * 2, out_channels=out_d, atrous_rates=[1, 3, 5, 7])
        self.conv1_s1=nn.Conv2d(in_d[3],out_d,1)
        self.conv1_s2 = nn.Conv2d(in_d[2], out_d, 1)
        self.conv1_s3 = nn.Conv2d(in_d[1], out_d, 1)
        self.conv3_x1_up_s1 = nn.Sequential(
            nn.Conv2d(self.in_d[4], self.mid_d, kernel_size=3, stride=1, padding=1),
            nn.BatchNorm2d(self.mid_d),
            nn.ReLU(inplace=True)
        )
        self.conv3_x2_s1 = nn.Sequential(
            nn.Conv2d(self.in_d[3], self.mid_d, kernel_size=3, stride=1, padding=1),
            nn.BatchNorm2d(self.mid_d),
            nn.ReLU(inplace=True)
        )

        self.conv3_s1_up_s2 = nn.Sequential(
            nn.Conv2d(self.out_d, self.mid_d, kernel_size=3, stride=1, padding=1),
            nn.BatchNorm2d(self.mid_d),
            nn.ReLU(inplace=True)
        )
        self.conv3_x3_s2 = nn.Sequential(
            nn.Conv2d(self.in_d[2], self.mid_d, kernel_size=3, stride=1, padding=1),
            nn.BatchNorm2d(self.mid_d),
            nn.ReLU(inplace=True)
        )

        self.conv3_s2_up_s3 = nn.Sequential(
            nn.Conv2d(self.out_d, self.mid_d, kernel_size=3, stride=1, padding=1),
            nn.BatchNorm2d(self.mid_d),
            nn.ReLU(inplace=True)
        )
        self.conv3_x4_s3 = nn.Sequential(
            nn.Conv2d(self.in_d[1], self.mid_d, kernel_size=3, stride=1, padding=1),
            nn.BatchNorm2d(self.mid_d),
            nn.ReLU(inplace=True)
        )

    def forward(self, x1, x2, x3, x4):

        x1_s1=self.conv3_x1_up_s1(x1)
        x1_up_s1 = F.interpolate(x1_s1, scale_factor=2, mode='bilinear')
        x2_s1=self.conv3_x2_s1(x2)
        s1=self.aspp_s1(torch.cat([x1_up_s1,x2_s1],1))+self.conv1_s1(x2)
        s1_s2 = self.conv3_s1_up_s2(s1)
        s1_up_s2 = F.interpolate(s1_s2, scale_factor=2, mode='bilinear')
        x3_s2 = self.conv3_x3_s2(x3)
        s2 = self.aspp_s2(torch.cat([s1_up_s2, x3_s2], 1)) + self.conv1_s2(x3)
        s2_s3 = self.conv3_s2_up_s3(s2)
        s2_up_s3 = F.interpolate(s2_s3, scale_factor=2, mode='bilinear')
        x4_s3 = self.conv3_x4_s3(x4)
        s3 = self.aspp_s3(torch.cat([s2_up_s3, x4_s3], 1)) + self.conv1_s3(x4)
        return s3

class EncoderTransformer_v1(nn.Module):
    def __init__(self, img_size=256, patch_size=3, in_chans=3, num_classes=2, embed_dims=[32, 64, 128, 256],
                 num_heads=[2, 2, 4, 8], mlp_ratios=[4, 4, 4, 4], qkv_bias=True, qk_scale=None, drop_rate=0.,
                 attn_drop_rate=0., drop_path_rate=0., norm_layer=nn.LayerNorm,
                 depths=[3, 3, 6, 18], sr_ratios=[8, 4, 2, 1]):
        super().__init__()
        self.num_classes = num_classes
        self.depths = depths
        self.embed_dims = embed_dims

        self.patch_embed1 = OverlapPatchEmbed(img_size=img_size, patch_size=7, stride=4, in_chans=16,
                                              embed_dim=embed_dims[0])
        self.patch_embed2 = OverlapPatchEmbed(img_size=img_size // 4, patch_size=patch_size, stride=2,
                                              in_chans=embed_dims[0],
                                              embed_dim=embed_dims[1])
        self.patch_embed3 = OverlapPatchEmbed(img_size=img_size // 8, patch_size=patch_size, stride=2,
                                              in_chans=embed_dims[1],
                                              embed_dim=embed_dims[2])
        self.patch_embed4 = OverlapPatchEmbed(img_size=img_size // 16, patch_size=patch_size, stride=2,
                                              in_chans=embed_dims[2],
                                              embed_dim=embed_dims[3])
        self.topk = [1, 4, 16, 64]
        dpr = [x.item() for x in torch.linspace(0, drop_path_rate, sum(depths))]
        cur = 0
        self.block1 = nn.ModuleList([Block(
            dim=embed_dims[0], num_heads=num_heads[0], mlp_ratio=mlp_ratios[0], qkv_bias=qkv_bias, qk_scale=qk_scale,
            drop=drop_rate, attn_drop=attn_drop_rate, drop_path=dpr[cur + i], norm_layer=norm_layer,
            sr_ratio=sr_ratios[0])
            for i in range(depths[0])])
        self.norm1 = norm_layer(embed_dims[0])
        self.c_block1 = DEM(
            dim=embed_dims[0], num_heads=num_heads[0], topk=self.topk[0], mlp_ratio=mlp_ratios[0], qkv_bias=qkv_bias,
            qk_scale=qk_scale,
            drop=drop_rate, attn_drop=attn_drop_rate, drop_path=dpr[cur], norm_layer=norm_layer,
            sr_ratio=sr_ratios[0])
        cur += depths[0]
        self.block2 = nn.ModuleList([Block(
            dim=embed_dims[1], num_heads=num_heads[1], mlp_ratio=mlp_ratios[1], qkv_bias=qkv_bias, qk_scale=qk_scale,
            drop=drop_rate, attn_drop=attn_drop_rate, drop_path=dpr[cur + i], norm_layer=norm_layer,
            sr_ratio=sr_ratios[1])
            for i in range(depths[1])])
        self.norm2 = norm_layer(embed_dims[1])
        self.c_block2 = DEM(
            dim=embed_dims[1], num_heads=num_heads[1], topk=self.topk[1], mlp_ratio=mlp_ratios[1], qkv_bias=qkv_bias,
            qk_scale=qk_scale,
            drop=drop_rate, attn_drop=attn_drop_rate, drop_path=dpr[cur], norm_layer=norm_layer,
            sr_ratio=sr_ratios[1])
        cur += depths[1]
        self.block3 = nn.ModuleList([Block(
            dim=embed_dims[2], num_heads=num_heads[2], mlp_ratio=mlp_ratios[2], qkv_bias=qkv_bias, qk_scale=qk_scale,
            drop=drop_rate, attn_drop=attn_drop_rate, drop_path=dpr[cur + i], norm_layer=norm_layer,
            sr_ratio=sr_ratios[2])
            for i in range(depths[2])])
        self.norm3 = norm_layer(embed_dims[2])
        self.c_block3 = DEM(
            dim=embed_dims[2], num_heads=num_heads[2], topk=self.topk[2], mlp_ratio=mlp_ratios[2], qkv_bias=qkv_bias,
            qk_scale=qk_scale,
            drop=drop_rate, attn_drop=attn_drop_rate, drop_path=dpr[cur], norm_layer=norm_layer,
            sr_ratio=sr_ratios[2])
        cur += depths[2]
        self.block4 = nn.ModuleList([Block(
            dim=embed_dims[3], num_heads=num_heads[3], mlp_ratio=mlp_ratios[3], qkv_bias=qkv_bias, qk_scale=qk_scale,
            drop=drop_rate, attn_drop=attn_drop_rate, drop_path=dpr[cur + i], norm_layer=norm_layer,
            sr_ratio=sr_ratios[3])
            for i in range(depths[3])])
        self.norm4 = norm_layer(embed_dims[3])
        self.c_block4 = DEM(
            dim=embed_dims[3], num_heads=num_heads[3], topk=self.topk[3], mlp_ratio=mlp_ratios[3], qkv_bias=qkv_bias,
            qk_scale=qk_scale,
            drop=drop_rate, attn_drop=attn_drop_rate, drop_path=dpr[cur], norm_layer=norm_layer,
            sr_ratio=sr_ratios[3])
        self.conv_first = conv_first(3)

        self.apply(self._init_weights)

    def _init_weights(self, m):
        if isinstance(m, nn.Linear):
            trunc_normal_(m.weight, std=.02)
            if isinstance(m, nn.Linear) and m.bias is not None:
                nn.init.constant_(m.bias, 0)
        elif isinstance(m, nn.LayerNorm):
            nn.init.constant_(m.bias, 0)
            nn.init.constant_(m.weight, 1.0)
        elif isinstance(m, nn.Conv2d):
            fan_out = m.kernel_size[0] * m.kernel_size[1] * m.out_channels
            fan_out //= m.groups
            m.weight.data.normal_(0, math.sqrt(2.0 / fan_out))
            if m.bias is not None:
                m.bias.data.zero_()

    def reset_drop_path(self, drop_path_rate):
        dpr = [x.item() for x in torch.linspace(0, drop_path_rate, sum(self.depths))]
        cur = 0
        for i in range(self.depths[0]):
            self.block1[i].drop_path.drop_prob = dpr[cur + i]

        cur += self.depths[0]
        for i in range(self.depths[1]):
            self.block2[i].drop_path.drop_prob = dpr[cur + i]

        cur += self.depths[1]
        for i in range(self.depths[2]):
            self.block3[i].drop_path.drop_prob = dpr[cur + i]

        cur += self.depths[2]
        for i in range(self.depths[3]):
            self.block4[i].drop_path.drop_prob = dpr[cur + i]

    def forward_features(self, x1,x2,  am_11 ,am_12,am_13,am_14,am_21, am_22, am_23, am_24):
        B = x1.shape[0]
        x1 = self.conv_first(x1)
        x2 = self.conv_first(x2)
        outs_1 = []
        outs_2 = []
        x1, H1, W1 = self.patch_embed1(x1,am_11 )
        x2, H1, W1 = self.patch_embed1(x2, am_21)
        for i, blk in enumerate(self.block1):
            x1 = blk(x1, H1, W1)
            x2 = blk(x2, H1, W1)
        x1, x2 = self.c_block1(x1, x2, H1, W1)
        x1 = self.norm1(x1)
        x2 = self.norm1(x2)
        x1 = x1.reshape(B, H1, W1, -1).permute(0, 3, 1, 2).contiguous()
        x2 = x2.reshape(B, H1, W1, -1).permute(0, 3, 1, 2).contiguous()
        outs_1.append(x1)
        outs_2.append(x2)

        x1, H1, W1 = self.patch_embed2(x1,am_12)
        x2, H1, W1 = self.patch_embed2(x2,am_22)
        for i, blk in enumerate(self.block2):
            x1 = blk(x1, H1, W1)
            x2 = blk(x2, H1, W1)
        x1, x2 = self.c_block2(x1, x2, H1, W1)
        x1 = self.norm2(x1)
        x2 = self.norm2(x2)
        x1 = x1.reshape(B, H1, W1, -1).permute(0, 3, 1, 2).contiguous()
        x2 = x2.reshape(B, H1, W1, -1).permute(0, 3, 1, 2).contiguous()
        outs_1.append(x1)
        outs_2.append(x2)

        # stage 3
        x1, H1, W1 = self.patch_embed3(x1,am_13)
        x2, H1, W1 = self.patch_embed3(x2,am_23)
        for i, blk in enumerate(self.block3):
            x1 = blk(x1, H1, W1)
            x2 = blk(x2, H1, W1)
        x1, x2 = self.c_block3(x1, x2, H1, W1)
        x1 = self.norm3(x1)
        x2 = self.norm3(x2)
        x1 = x1.reshape(B, H1, W1, -1).permute(0, 3, 1, 2).contiguous()
        x2 = x2.reshape(B, H1, W1, -1).permute(0, 3, 1, 2).contiguous()
        outs_1.append(x1)
        outs_2.append(x2)

        # stage 4
        x1, H1, W1 = self.patch_embed4(x1,am_14)
        x2, H1, W1 = self.patch_embed4(x2,am_24)
        for i, blk in enumerate(self.block4):
            x1 = blk(x1, H1, W1)
            x2 = blk(x2, H1, W1)
        x1, x2 = self.c_block4(x1, x2, H1, W1)
        x1 = self.norm4(x1)
        x2 = self.norm4(x2)
        x1 = x1.reshape(B, H1, W1, -1).permute(0, 3, 1, 2).contiguous()
        x2 = x2.reshape(B, H1, W1, -1).permute(0, 3, 1, 2).contiguous()
        outs_1.append(x1)
        outs_2.append(x2)

        return outs_1, outs_2

    def forward(self, x1, x2, am_11 ,am_12,am_13,am_14,am_21, am_22, am_23, am_24):
        o1,o2 = self.forward_features(x1,  x2,am_11 ,am_12,am_13,am_14,am_21, am_22, am_23, am_24)
        return o1,o2

class DecoderTransformer_v1(nn.Module):


    def __init__(self, input_transform='multiple_select', in_index=[0, 1, 2, 3], align_corners=True,
                 in_channels=[32, 64, 128, 256], embedding_dim=64, output_nc=2,
                 decoder_softmax=False, feature_strides=[2, 4, 8, 16]):
        super(DecoderTransformer_v1, self).__init__()
        # assert
        assert len(feature_strides) == len(in_channels)
        assert min(feature_strides) == feature_strides[0]

        self.feature_strides = feature_strides
        self.input_transform = input_transform
        self.in_index = in_index
        self.align_corners = align_corners
        self.in_channels = in_channels
        self.embedding_dim = embedding_dim
        self.output_nc = output_nc
        c1_in_channels, c2_in_channels, c3_in_channels, c4_in_channels = self.in_channels

        self.linear_c4 = MLP(input_dim=c4_in_channels, embed_dim=self.embedding_dim)
        self.linear_c3 = MLP(input_dim=c3_in_channels, embed_dim=self.embedding_dim)
        self.linear_c2 = MLP(input_dim=c2_in_channels, embed_dim=self.embedding_dim)
        self.linear_c1 = MLP(input_dim=c1_in_channels, embed_dim=self.embedding_dim)

        self.diff_c4 = conv_diff(in_channels=2 * self.embedding_dim, out_channels=self.embedding_dim)
        self.diff_c3 = conv_diff(in_channels=3 * self.embedding_dim, out_channels=self.embedding_dim)
        self.diff_c2 = conv_diff(in_channels=3 * self.embedding_dim, out_channels=self.embedding_dim)
        self.diff_c1 = conv_diff(in_channels=3 * self.embedding_dim, out_channels=self.embedding_dim)

        self.make_pred_c4 = make_prediction(in_channels=self.embedding_dim, out_channels=self.output_nc)
        self.make_pred_c3 = make_prediction(in_channels=self.embedding_dim, out_channels=self.output_nc)
        self.make_pred_c2 = make_prediction(in_channels=self.embedding_dim, out_channels=self.output_nc)
        self.make_pred_c1 = make_prediction(in_channels=self.embedding_dim, out_channels=self.output_nc)
        self.make_pred_c = make_prediction(in_channels=self.embedding_dim*3, out_channels=self.output_nc)

        self.make_sobel=make_sobel(in_chan=self.embedding_dim)

        self.mobile_dims = [24, 32, 96, 320]
        self.abs_nam=abs_nam()

        self.convd2x = UpsampleConvLayer(self.embedding_dim*3, self.embedding_dim, kernel_size=4, stride=2)
        self.dense_2x = nn.Sequential(ResidualBlock(self.embedding_dim))
        self.convd1x = UpsampleConvLayer(self.embedding_dim, self.embedding_dim, kernel_size=4, stride=2)
        self.dense_1x = nn.Sequential(ResidualBlock(self.embedding_dim))
        self.change_probability = ConvLayer(self.embedding_dim, self.output_nc, kernel_size=3, stride=1, padding=1)

        self.output_softmax = decoder_softmax
        self.active = nn.Sigmoid()
        self.SEM=SEM(self.embedding_dim)

    def _transform_inputs(self, inputs):
        """Transform inputs for decoder.
        Args:
            inputs (list[Tensor]): List of multi-level img features.
        Returns:
            Tensor: The transformed inputs
        """

        if self.input_transform == 'resize_concat':
            inputs = [inputs[i] for i in self.in_index]
            upsampled_inputs = [
                resize(
                    input=x,
                    size=inputs[0].shape[2:],
                    mode='bilinear',
                    align_corners=self.align_corners) for x in inputs
            ]
            inputs = torch.cat(upsampled_inputs, dim=1)
        elif self.input_transform == 'multiple_select':
            inputs = [inputs[i] for i in self.in_index]
        else:
            inputs = inputs[self.in_index]

        return inputs

    def forward(self, inputs1, inputs2,diff_1,diff_2,diff_3,diff_4):
        x_1 = self._transform_inputs(inputs1)
        x_2 = self._transform_inputs(inputs2)
        c1_1, c2_1, c3_1, c4_1 = x_1
        c1_2, c2_2, c3_2, c4_2 = x_2

        outputs = []

        n, _, h, w = c4_1.shape

        diff_4=self.abs_nam(diff_4,diff_3,diff_2,diff_1)
        # Stage 4: x1/32 scale
        _c4_1 = self.linear_c4(c4_1).permute(0, 2, 1).reshape(n, -1, c4_1.shape[2], c4_1.shape[3])
        _c4_2 = self.linear_c4(c4_2).permute(0, 2, 1).reshape(n, -1, c4_2.shape[2], c4_2.shape[3])

        _c4 = self.diff_c4(torch.cat([_c4_1, _c4_2], dim=1))

        p_c4 = self.make_pred_c4(_c4)
        outputs.append(p_c4)
        _c4_up = resize(_c4, size=c3_2.size()[2:], mode='bilinear', align_corners=False)

        # Stage 3: x1/16 scale
        _c3_1 = self.linear_c3(c3_1).permute(0, 2, 1).reshape(n, -1, c3_1.shape[2], c3_1.shape[3])
        _c3_2 = self.linear_c3(c3_2).permute(0, 2, 1).reshape(n, -1, c3_2.shape[2], c3_2.shape[3])

        _c3 = self.diff_c3(torch.cat([_c3_1, _c3_2,_c4_up], dim=1))
        p_c3 = self.make_pred_c3(_c3)
        outputs.append(p_c3)
        _c3_up = resize(_c3, size=c2_2.size()[2:], mode='bilinear', align_corners=False)

        # Stage 2: x1/8 scale
        _c2_1 = self.linear_c2(c2_1).permute(0, 2, 1).reshape(n, -1, c2_1.shape[2], c2_1.shape[3])
        _c2_2 = self.linear_c2(c2_2).permute(0, 2, 1).reshape(n, -1, c2_2.shape[2], c2_2.shape[3])

        _c2 = self.diff_c2(torch.cat([_c2_1, _c2_2,_c3_up], dim=1))
        p_c2 = self.make_pred_c2(_c2)
        outputs.append(p_c2)
        _c2_up = resize(_c2, size=c1_2.size()[2:], mode='bilinear', align_corners=False)

        # Stage 1: x1/4 scale
        _c1_1 = self.linear_c1(c1_1).permute(0, 2, 1).reshape(n, -1, c1_1.shape[2], c1_1.shape[3])
        _c1_2 = self.linear_c1(c1_2).permute(0, 2, 1).reshape(n, -1, c1_2.shape[2], c1_2.shape[3])

        _c1 = self.diff_c1(torch.cat([_c1_1, _c1_2,_c2_up], dim=1))
        p_c1 = self.make_pred_c1(_c1)
        outputs.append(p_c1)

        diff_4_pred=self.make_sobel(diff_4)
        outputs.append(diff_4_pred)

        _c=self.SEM(diff_4, _c1)
        p_c = self.make_pred_c(_c)
        #outputs.append(p_c)
        # Upsampling x2 (x1/2 scale)
        x = self.convd2x(_c)
        # Residual block
        x = self.dense_2x(x)
        # Upsampling x2 (x1 scale)
        x = self.convd1x(x)
        # Residual block
        x = self.dense_1x(x)

        # Final prediction
        cp = self.change_probability(x)

        outputs.append(cp)

        if self.output_softmax:
            temp = outputs
            outputs = []
            for pred in temp:
                outputs.append(self.active(pred))

        return outputs


def exact_feature_distribution_matching_mask(content, style):
    assert (content.size() == style.size()) ## content and style features should share the same shape

    B, C, W, H = content.size(0), content.size(1), content.size(2), content.size(3)
    mask = torch.rand((B, C, W*H)).cuda()
    _, index_content = torch.sort(content.view(B,C,-1))  ## sort content feature
    value_style, _ = torch.sort(style.view(B,C,-1))      ## sort style feature
    inverse_index = index_content.argsort(-1)

    transferred_content = content.view(B,C,-1) + value_style.gather(-1, inverse_index)*(1-mask) - content.view(B,C,-1).detach()*(1-mask)
    return transferred_content.view(B, C, W, H)

class CAIFNet(nn.Module):

    def __init__(self, input_nc=3, output_nc=2, decoder_softmax=False, embed_dim=256):
        super(CAIFNet, self).__init__()
        # Transformer Encoder
        self.embed_dims = [48, 64, 192, 640]#64, 128, 320, 512
        self.depths = [2, 2, 3, 2]  # 3, 3, 4, 3
        self.embedding_dim = embed_dim
        self.drop_rate = 0.1
        self.attn_drop = 0.1
        self.drop_path_rate = 0.1

        self.Tenc_x2 = EncoderTransformer_v1(img_size=256, patch_size=7, in_chans=input_nc, num_classes=output_nc,
                                             embed_dims=self.embed_dims,
                                             num_heads=[1, 2, 4, 8], mlp_ratios=[4, 4, 4, 4], qkv_bias=True,
                                             qk_scale=None, drop_rate=self.drop_rate,
                                             attn_drop_rate=self.attn_drop, drop_path_rate=self.drop_path_rate,
                                             norm_layer=partial(nn.LayerNorm, eps=1e-6),
                                             depths=self.depths, sr_ratios=[8, 4, 2, 1])

        # Transformer Decoder
        self.New_TDec_x2 = DecoderTransformer_v1(input_transform='multiple_select', in_index=[0, 1, 2, 3],
                                             align_corners=False,
                                             in_channels=self.embed_dims, embedding_dim=64,
                                             output_nc=output_nc,
                                             decoder_softmax=decoder_softmax, feature_strides=[2, 4, 8, 16])

        self.backbone = Mobilev2_for_single.mobilenet_v2(pretrained=True)
    def forward(self, x1, x2,flag,epoch,max_epoch):
        x1_ori=x1
        x2_ori=x2
        ####APM
        if flag==1:
            if epoch<min(200,max_epoch):
                if random.random()<0.5:
                    B, C, H, W = x1.shape

                    x1_freq = torch.fft.rfft2(x1_ori, norm='backward')
                    x1_pha = torch.angle(x1_freq)
                    x1_mag = torch.abs(x1_freq)

                    x2_freq = torch.fft.rfft2(x2_ori, norm='backward')
                    x2_mag = torch.abs(x2_freq)

                    x1_mag_match = exact_feature_distribution_matching_mask(x1_mag, x2_mag)

                    x1_real = x1_mag_match * torch.cos(x1_pha)
                    x1_imag = x1_mag_match * torch.sin(x1_pha)

                    x1_complex = torch.complex(x1_real, x1_imag)

                    x1 = ((torch.fft.irfft2(x1_complex, s=(H, W), norm='backward')))

                if random.random()<0.5:
                    B, C, H, W = x1.shape

                    x1_freq = torch.fft.rfft2(x1_ori, norm='backward')
                    x1_mag = torch.abs(x1_freq)

                    x2_freq = torch.fft.rfft2(x2_ori, norm='backward')
                    x2_pha = torch.angle(x2_freq)
                    x2_mag = torch.abs(x2_freq)

                    x2_mag_match = exact_feature_distribution_matching_mask(x2_mag, x1_mag)

                    x2_real = x2_mag_match * torch.cos(x2_pha)
                    x2_imag = x2_mag_match * torch.sin(x2_pha)

                    x2_complex = torch.complex(x2_real, x2_imag)

                    x2 = ((torch.fft.irfft2(x2_complex, s=(H, W), norm='backward')))

        res_1,res_2,am_list_1,am_list_2 = self.backbone(x1,x2) #CNN
        x1_1,x1_2,x1_3,x1_4=res_1
        x2_1, x2_2, x2_3, x2_4 = res_2

        diff_1 = abs(x1_1 - x2_1)
        diff_2 = abs(x1_2 - x2_2)
        diff_3 = abs(x1_3 - x2_3)
        diff_4 = abs(x1_4 - x2_4)
        am_11 ,am_12,am_13,am_14= am_list_1
        am_21, am_22, am_23, am_24 = am_list_2
        fx1 ,fx2= self.Tenc_x2(x1, x2,am_11 ,am_12,am_13,am_14,am_21, am_22, am_23, am_24) #Transformer and DEM
        cp = self.New_TDec_x2(fx1, fx2,diff_1,diff_2,diff_3,diff_4)  #BDB and MDB and SEM

        return cp


