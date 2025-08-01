import os
from os.path import join as pjoin

import torch

from models.mask_transformer.transformer import MaskTransformer, ResidualTransformer
from models.vq.model import RVQVAE

from options.eval_option import EvalT2MOptions
from utils.get_opt import get_opt
from motion_loaders.dataset_motion_loader import get_dataset_motion_loader
from models.t2m_eval_wrapper import EvaluatorModelWrapper

import utils.eval_t2m as eval_t2m
from utils.fixseed import fixseed

import numpy as np
from models.mask_transformer.control_transformer import ControlTransformer

def load_vq_model(vq_opt):
    # opt_path = pjoin(opt.checkpoints_dir, opt.dataset_name, opt.vq_name, 'opt.txt')
    vq_model = RVQVAE(vq_opt,
                dim_pose,
                vq_opt.nb_code,
                vq_opt.code_dim,
                vq_opt.output_emb_width,
                vq_opt.down_t,
                vq_opt.stride_t,
                vq_opt.width,
                vq_opt.depth,
                vq_opt.dilation_growth_rate,
                vq_opt.vq_act,
                vq_opt.vq_norm)
    ckpt = torch.load(pjoin(vq_opt.checkpoints_dir, vq_opt.dataset_name, vq_opt.name, 'model', 'net_best_fid.tar'),
                            map_location=opt.device)
    model_key = 'vq_model' if 'vq_model' in ckpt else 'net'
    vq_model.load_state_dict(ckpt[model_key])
    print(f'Loading VQ Model {vq_opt.name} Completed!')
    return vq_model, vq_opt

def load_trans_model(model_opt, which_model):
    t2m_transformer = MaskTransformer(code_dim=model_opt.code_dim,
                                      cond_mode='text',
                                      latent_dim=model_opt.latent_dim,
                                      ff_size=model_opt.ff_size,
                                      num_layers=model_opt.n_layers,
                                      num_heads=model_opt.n_heads,
                                      dropout=model_opt.dropout,
                                      clip_dim=512,
                                      cond_drop_prob=model_opt.cond_drop_prob,
                                      clip_version=clip_version,
                                      opt=model_opt)
    ckpt = torch.load(pjoin(model_opt.checkpoints_dir, model_opt.dataset_name, model_opt.name, 'model', which_model),
                      map_location=opt.device)
    model_key = 't2m_transformer' if 't2m_transformer' in ckpt else 'trans'
    # print(ckpt.keys())
    missing_keys, unexpected_keys = t2m_transformer.load_state_dict(ckpt[model_key], strict=False)
    assert len(unexpected_keys) == 0
    assert all([k.startswith('clip_model.') for k in missing_keys])
    print(f'Loading Mask Transformer {opt.name} from epoch {ckpt["ep"]}!')
    return t2m_transformer

def load_ctrltrans_model(model_opt, opt, which_model):
    ct2m_transformer = ControlTransformer(code_dim=model_opt.code_dim,
                                      cond_mode='text',
                                      latent_dim=model_opt.latent_dim,
                                      ff_size=model_opt.ff_size,
                                      num_layers=model_opt.n_layers,
                                      num_heads=model_opt.n_heads,
                                      dropout=model_opt.dropout,
                                      clip_dim=512,
                                      cond_drop_prob=model_opt.cond_drop_prob,
                                      clip_version=clip_version,
                                      opt=model_opt,
                                      mean=torch.tensor(eval_val_loader.dataset.mean).cuda(),
                                      std=torch.tensor(eval_val_loader.dataset.std).cuda(),
                                    #   trans_path='./checkpoints/t2m/1_mtrans_lossAllMaskNoMask/model/latest.tar',
                                      vq_model=vq_model,
                                      control=opt.control)
    ct2m_transformer.cuda()
    ckpt = torch.load(pjoin(model_opt.checkpoints_dir, model_opt.dataset_name, opt.ctrl_name, 'model', which_model),
                      map_location=opt.device)
    missing_keys, unexpected_keys = ct2m_transformer.load_state_dict(ckpt['ct2m_transformer'], strict=False)
    return ct2m_transformer

def load_res_model(res_opt):
    res_opt.num_quantizers = vq_opt.num_quantizers
    res_opt.num_tokens = vq_opt.nb_code
    res_transformer = ResidualTransformer(code_dim=vq_opt.code_dim,
                                            cond_mode='text',
                                            latent_dim=res_opt.latent_dim,
                                            ff_size=res_opt.ff_size,
                                            num_layers=res_opt.n_layers,
                                            num_heads=res_opt.n_heads,
                                            dropout=res_opt.dropout,
                                            clip_dim=512,
                                            shared_codebook=vq_opt.shared_codebook,
                                            cond_drop_prob=res_opt.cond_drop_prob,
                                            # codebook=vq_model.quantizer.codebooks[0] if opt.fix_token_emb else None,
                                            share_weight=res_opt.share_weight,
                                            clip_version=clip_version,
                                            opt=res_opt)
    res_transformer.cuda()
    ckpt = torch.load(pjoin(res_opt.checkpoints_dir, res_opt.dataset_name, res_opt.name, 'model', 'net_best_fid.tar'),
                      map_location=opt.device)
    missing_keys, unexpected_keys = res_transformer.load_state_dict(ckpt['res_transformer'], strict=False)

    ### Control Res
    # from models.mask_transformer.control_res import ControlRes
    # res_transformer = ControlRes(code_dim=vq_opt.code_dim,
    #                                         cond_mode='text',
    #                                         latent_dim=res_opt.latent_dim,
    #                                         ff_size=res_opt.ff_size,
    #                                         num_layers=res_opt.n_layers,
    #                                         num_heads=res_opt.n_heads,
    #                                         dropout=res_opt.dropout,
    #                                         clip_dim=512,
    #                                         shared_codebook=vq_opt.shared_codebook,
    #                                         cond_drop_prob=res_opt.cond_drop_prob,
    #                                         share_weight=True, # <<<<<<<<<<<<<<<<<<<<<< HARD CODED, the save was wrong
    #                                         clip_version=clip_version,
    #                                         opt=res_opt,
    #                                         mean=torch.tensor(eval_val_loader.dataset.mean, requires_grad=False).cuda(),
    #                                         std=torch.tensor(eval_val_loader.dataset.std, requires_grad=False).cuda(),
    #                                         # res_path=f'./checkpoints/t2m/{opt.res_name}/model/net_best_fid.tar',
    #                                         vq_model=vq_model,
    #                                         control=opt.control)
    # res_transformer.cuda()
    # ckpt = torch.load(pjoin(res_opt.checkpoints_dir, res_opt.dataset_name, res_opt.name, 'model', 'latest.tar'), map_location=opt.device)
    # missing_keys, unexpected_keys = res_transformer.load_state_dict(ckpt['ct2m_transformer'], strict=False)
    assert len(unexpected_keys) == 0
    assert all([k.startswith('clip_model.') for k in missing_keys])
    print(f'Loading Residual Transformer {res_opt.name} from epoch {ckpt["ep"]}!')
    return res_transformer

if __name__ == '__main__':
    parser = EvalT2MOptions()
    opt = parser.parse()
    fixseed(opt.seed)

    opt.device = torch.device("cpu" if opt.gpu_id == -1 else "cuda:" + str(opt.gpu_id))
    torch.autograd.set_detect_anomaly(True)

    dim_pose = 251 if opt.dataset_name == 'kit' else 263

    if opt.dataset_name == 't2m':
        opt.data_root = './dataset/HumanML3D'
        opt.motion_dir = pjoin(opt.data_root, 'new_joint_vecs')
        opt.joints_num = 22
        opt.max_motion_len = 55
        dim_pose = 263
        radius = 4
        fps = 20
        # kinematic_chain = t2m_kinematic_chain
        dataset_opt_path = './checkpoints/t2m/Comp_v6_KLD005/opt.txt'

    elif opt.dataset_name == 'kit': #TODO
        opt.data_root = './dataset/KIT-ML'
        opt.motion_dir = pjoin(opt.data_root, 'new_joint_vecs')
        opt.joints_num = 21
        radius = 240 * 8
        fps = 12.5
        dim_pose = 251
        opt.max_motion_len = 55
        # kinematic_chain = kit_kinematic_chain
        dataset_opt_path = './checkpoints/kit/Comp_v6_KLD005/opt.txt'

    # out_dir = pjoin(opt.check)
    model_name = opt.ctrl_name if opt.ctrl_name is not None else opt.name
    root_dir = pjoin(opt.checkpoints_dir, opt.dataset_name, model_name)
    model_dir = pjoin(root_dir, 'model')
    out_dir = pjoin(root_dir, 'eval')
    os.makedirs(out_dir, exist_ok=True)

    out_path = pjoin(out_dir, "%s.log"%opt.ext)

    f = open(pjoin(out_path), 'w')
    print(opt, file=f, flush=True)

    model_opt_path = pjoin(root_dir, 'opt.txt')
    model_opt = get_opt(model_opt_path, device=opt.device)
    clip_version = 'ViT-B/32'

    vq_opt_path = pjoin(opt.checkpoints_dir, opt.dataset_name, model_opt.vq_name, 'opt.txt')
    vq_opt = get_opt(vq_opt_path, device=opt.device)
    vq_model, vq_opt = load_vq_model(vq_opt)

    model_opt.num_tokens = vq_opt.nb_code
    model_opt.num_quantizers = vq_opt.num_quantizers
    model_opt.code_dim = vq_opt.code_dim



    dataset_opt_path = 'checkpoints/kit/Comp_v6_KLD005/opt.txt' if opt.dataset_name == 'kit' \
        else 'checkpoints/t2m/Comp_v6_KLD005/opt.txt'

    wrapper_opt = get_opt(dataset_opt_path, torch.device('cuda'))
    eval_wrapper = EvaluatorModelWrapper(wrapper_opt)

    ##### ---- Dataloader ---- #####
    opt.nb_joints = 21 if opt.dataset_name == 'kit' else 22

    eval_val_loader, _ = get_dataset_motion_loader(dataset_opt_path, 32, 'test', device=opt.device)



    res_opt_path = pjoin(opt.checkpoints_dir, opt.dataset_name, opt.res_name, 'opt.txt')
    res_opt = get_opt(res_opt_path, device=opt.device)
    res_model = load_res_model(res_opt)
    assert res_opt.vq_name == model_opt.vq_name

    # model_dir = pjoin(opt.)
    for file in os.listdir(model_dir):
        if opt.which_epoch != "all" and opt.which_epoch not in file:
            continue
        print('loading checkpoint {}'.format(file))

        if opt.ctrl_name is None:
            ct2m_transformer = load_trans_model(model_opt, file)
            ct2m_transformer.eval()
            vq_model.eval()
            res_model.eval()

            ct2m_transformer.to(opt.device)
            vq_model.to(opt.device)
            res_model.to(opt.device)
        
        else:
            ########## Control Info ##########
            ct2m_transformer = load_ctrltrans_model(model_opt, opt, file)
            ct2m_transformer.res_model = res_model
            ct2m_transformer.res_model.process_embed_proj_weight()
            ct2m_transformer.ctrl_eval()

            ct2m_transformer.vq_model = vq_model
            ########################################

        fid = []
        div = []
        top1 = []
        top2 = []
        top3 = []
        skate_ratio = []
        matching = []
        mm = []
        traj_fail_50cm = []
        kps_fail_50cm = []
        kps_mean_err = []
        avoid_dist = []

        repeat_time = 10
        for i in range(repeat_time):
            with torch.no_grad():
                best_fid, best_div, Rprecision, best_matching, best_skate_ratio, best_mm, traj_err, _avoid_dist, kps_mean = \
                    eval_t2m.evaluation_mask_transformer_test_plus_res(eval_val_loader, vq_model, res_model, ct2m_transformer, None,
                                                                        i, eval_wrapper=eval_wrapper,
                                                            time_steps=opt.time_steps, cond_scale=opt.cond_scale,
                                                            temperature=opt.temperature, topkr=opt.topkr,
                                                                        force_mask=opt.force_mask, cal_mm=True, f=f, pred_num_batch=8,
                                                                        control=opt.control, 
                                                                        density=opt.density,
                                                                        opt=opt)
            fid.append(best_fid)
            div.append(best_div)
            top1.append(Rprecision[0])
            top2.append(Rprecision[1])
            top3.append(Rprecision[2])
            matching.append(best_matching)
            skate_ratio.append(best_skate_ratio)
            mm.append(best_mm)
            traj_fail_50cm.append(traj_err[eval_t2m.traj_err_key.index('traj_fail_50cm (Traj err)')])
            kps_fail_50cm.append(traj_err[eval_t2m.traj_err_key.index('kps_fail_50cm (Loc. err)')])
            kps_mean_err.append(traj_err[eval_t2m.traj_err_key.index('kps_mean_err(m) (Avg. err)')])
            avoid_dist.append(_avoid_dist)

    fid = np.array(fid)
    div = np.array(div)
    top1 = np.array(top1)
    top2 = np.array(top2)
    top3 = np.array(top3)
    matching = np.array(matching)
    mm = np.array(mm)

    print(f'{file} final result:')
    print(f'{file} final result:', file=f, flush=True)

    msg_final = f"\tFID: {np.mean(fid):.5f}, conf. {np.std(fid) * 1.96 / np.sqrt(repeat_time):.5f}\n" \
                f"\tDiversity: {np.mean(div):.5f}, conf. {np.std(div) * 1.96 / np.sqrt(repeat_time):.5f}\n" \
                f"\tTOP1: {np.mean(top1):.5f}, conf. {np.std(top1) * 1.96 / np.sqrt(repeat_time):.5f}, TOP2. {np.mean(top2):.5f}, conf. {np.std(top2) * 1.96 / np.sqrt(repeat_time):.5f}, TOP3. {np.mean(top3):.5f}, conf. {np.std(top3) * 1.96 / np.sqrt(repeat_time):.5f}\n" \
                f"\tMatching: {np.mean(matching):.5f}, conf. {np.std(matching) * 1.96 / np.sqrt(repeat_time):.5f}\n" \
                f"\tskate_ratio: {np.mean(skate_ratio):.5f}, conf. {np.std(skate_ratio) * 1.96 / np.sqrt(repeat_time):.5f}\n" \
                f"\tMultimodality:{np.mean(mm):.5f}, conf.{np.std(mm) * 1.96 / np.sqrt(repeat_time):.5f}\n" \
                f"\ttraj_fail_50cm:{np.mean(traj_fail_50cm):.5f}, conf.{np.std(traj_fail_50cm) * 1.96 / np.sqrt(repeat_time):.5f}\n" \
                f"\tkps_fail_50cm:{np.mean(kps_fail_50cm):.5f}, conf.{np.std(kps_fail_50cm) * 1.96 / np.sqrt(repeat_time):.5f}\n" \
                f"\tkps_mean_err:{np.mean(kps_mean_err):.5f}, conf.{np.std(kps_mean_err) * 1.96 / np.sqrt(repeat_time):.5f}\n\n" \
                f"\tavoid_dist: {np.mean(avoid_dist):.5f}, conf. {np.std(avoid_dist) * 1.96 / np.sqrt(repeat_time):.5f}\n" \
    # logger.info(msg_final)
    print(msg_final)
    print(msg_final, file=f, flush=True)

    f.close()


# python eval_t2m_trans.py --name t2m_nlayer8_nhead6_ld384_ff1024_cdp0.1_vq --dataset_name t2m --gpu_id 3 --cond_scale 4 --time_steps 18 --temperature 1 --topkr 0.9 --gumbel_sample --ext cs4_ts18_tau1_topkr0.9_gs