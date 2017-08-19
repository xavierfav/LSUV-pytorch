import numpy as np
import torch
import torch.nn.init
import torch.nn as nn

gg = {}
gg['hook_position'] = 0
gg['total_fc_conv_layers'] = 0
gg['done_counter'] = -1
gg['hook'] = None
gg['act_dict'] = {}
gg['counter_to_apply_correction'] = 0
gg['correction_needed'] = False
gg['current_coef'] = 1.0

# Orthonorm init code is taked from Lasagne
# https://github.com/Lasagne/Lasagne/blob/master/lasagne/init.py
def svd_orthonormal(w):
    shape = w.shape
    if len(shape) < 2:
        raise RuntimeError("Only shapes of length 2 or more are supported.")
    flat_shape = (shape[0], np.prod(shape[1:]))
    a = w;
    u, _, v = np.linalg.svd(a, full_matrices=False)
    q = u if u.shape == flat_shape else v
    print shape, flat_shape
    q = q.reshape(shape)
    return q

def store_activations(self, input, output):
    gg['act_dict'] = output.data.cpu().numpy();
    return


def add_current_hook(m):
    if gg['hook'] is not None:
        return
    if (isinstance(m, nn.Conv2d)) or (isinstance(m, nn.Linear)):
        #print 'trying to hook to', m
        if gg['hook_position'] > gg['done_counter']:
            gg['hook'] = m.register_forward_hook(store_activations)
            #print 'layer = ', gg['hook_position'], m
        else:
            #print 'already done, skipping'
            gg['hook_position'] += 1
    return

def count_conv_fc_layers(m):
    if (isinstance(m, nn.Conv2d)) or (isinstance(m, nn.Linear)):
        gg['total_fc_conv_layers'] +=1
    return

def remove_hooks(hooks):
    for h in hooks:
        h.remove()
    return
def orthogonal_weights_init(m):
    if isinstance(m, nn.Conv2d) or isinstance(m, nn.Linear):
        w_ortho = svd_orthonormal(m.weight.data.cpu().numpy())
        #print w_ortho 
        m.weight.data.copy_(torch.from_numpy(w_ortho))
    return

def apply_weights_correction(m):
    if gg['hook'] is None:
        return
    if not gg['correction_needed']:
        return
    if (isinstance(m, nn.Conv2d)) or (isinstance(m, nn.Linear)):
        if gg['counter_to_apply_correction'] < gg['hook_position']:
            gg['counter_to_apply_correction'] += 1
        else:
            #print 'weights norm before = ', m.weight.data.norm()
            m.weight.data *= gg['current_coef']
            #print 'weights norm after = ', m.weight.data.norm()
            gg['correction_needed'] = False
            return
    return

def LSUVinit(model,data, needed_std = 1.0, std_tol = 0.1, max_attempts = 10, do_orthonorm = True, cuda = False):
    if cuda:
        model = model.cuda()
        data = data.cuda()
    else:
        model = model.cpu()
        data = data.cpu() 
    print 'Starting LSUV'
    model.apply(count_conv_fc_layers)
    print 'Total layers to process:', gg['total_fc_conv_layers']
    if do_orthonorm:
        model.apply(orthogonal_weights_init)
        print 'Orthonorm done'
        if cuda:
            model = model.cuda()
    for layer_idx in range(gg['total_fc_conv_layers']):
        print layer_idx
        model.apply(add_current_hook)
        out = model(data)
        current_std = gg['act_dict'].std()
        print 'std at layer ',layer_idx, ' = ', current_std
        #print  gg['act_dict'].shape
        attempts = 0
        while (np.abs(current_std - needed_std) > std_tol):
            gg['current_coef'] =  needed_std / (current_std  + 1e-8);
            gg['correction_needed'] = True
            model.apply(apply_weights_correction)
            if cuda:
                model = model.cuda()
            out = model(data)
            current_std = gg['act_dict'].std()
            print 'std at layer ',layer_idx, ' = ', current_std
            attempts+=1
            if attempts > max_attempts:
                print 'Cannot converge in ', max_attempts, 'iterations'
                break
        if gg['hook'] is not None:
           gg['hook'].remove()
        gg['done_counter']+=1
        gg['hook']  = None
        print 'finish at layer',layer_idx 
    print 'LSUV init done!'
    if not cuda:
        model = model.cpu()
    return model
