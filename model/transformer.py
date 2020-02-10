"""
对transformer encoder的paddle实现。
"""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from functools import partial
import numpy as np
import paddle.fluid as fluid
import paddle.fluid.layers as layers


def transformer_encoder(inputs,
                        attention_bias,
                        num_attention_layers,
                        num_attention_heads,
                        hidden_state_size,
                        key_size,
                        value_size,
                        inner_hidden_size,
                        attention_dropout,
                        activate_dropout,
                        post_and_pre_process_dropout,
                        hidden_act,
                        preprocess_cmd="n",
                        postprocess_cmd="da",
                        param_initializer=None,
                        name=''):

    enc_input = inputs
    for i in range(num_attention_layers):
        enc_output = encoder_layer(
            enc_input,
            attention_bias,
            num_attention_heads,
            hidden_state_size,
            key_size,
            value_size,
            inner_hidden_size,
            attention_dropout,
            activate_dropout,
            post_and_pre_process_dropout,
            hidden_act,
            preprocess_cmd,
            postprocess_cmd,
            param_initializer=param_initializer,
            name=name + '_layer_' + str(i))
        enc_input = enc_output

    enc_output = pre_process_layer(
        enc_output, preprocess_cmd, post_and_pre_process_dropout, name="post_encoder")

    return enc_output


def encoder_layer(inputs,
                  attention_bias,
                  num_attention_heads,
                  hidden_state_size,
                  key_size,
                  value_size,
                  inner_hidden_size,
                  attention_dropout,
                  activate_dropout,
                  post_and_pre_process_dropout,
                  hidden_act,
                  preprocess_cmd="n",
                  postprocess_cmd="da",
                  param_initializer=None,
                  name=''
                  ):
    attn_output = multi_head_attention(
        pre_process_layer(
            inputs,
            preprocess_cmd,
            post_and_pre_process_dropout,
            name=name + '_pre_att'),
        None,
        None,
        attention_bias,
        key_size,
        value_size,
        hidden_state_size,
        num_attention_heads,
        attention_dropout,
        param_initializer=param_initializer,
        name=name + '_multi_head_att')
    attn_output = post_process_layer(
        inputs,
        attn_output,
        postprocess_cmd,
        post_and_pre_process_dropout,
        name=name + '_post_att')

    ffd_output = feed_forward_layer(
        pre_process_layer(
            attn_output,
            preprocess_cmd,
            post_and_pre_process_dropout,
            name=name + '_pre_ffn'),
        hidden_state_size,
        inner_hidden_size,
        activate_dropout,
        hidden_act,
        param_initializer=param_initializer,
        name=name + '_ffn')

    return post_process_layer(
        attn_output,
        ffd_output,
        postprocess_cmd,
        post_and_pre_process_dropout,
        name=name + '_post_ffn')


# 对encoder_layer中前馈层的实现
def feed_forward_layer(x,
                       hidden_size,
                       inner_hidden_size,
                       dropout_rate,
                       hidden_act,
                       param_initializer=None,
                       name='ffn'):

    hidden = layers.fc(input=x,
                       size=inner_hidden_size,
                       num_flatten_dims=2,
                       act=hidden_act,
                       param_attr=fluid.ParamAttr(
                           name=name + '_fc_0.w_0',
                           initializer=param_initializer),
                       bias_attr=name + '_fc_0.b_0')
    if dropout_rate:
        hidden = layers.dropout(
            hidden,
            dropout_prob=dropout_rate,
            dropout_implementation="upscale_in_train",
            is_test=False)
    out = layers.fc(input=hidden,
                    size=hidden_size,
                    num_flatten_dims=2,
                    param_attr=fluid.ParamAttr(
                        name=name + '_fc_1.w_0', initializer=param_initializer),
                    bias_attr=name + '_fc_1.b_0')
    return out


def pre_post_process_layer(prev_out, out, process_cmd, dropout_rate=0.,
                           name=''):
    """
    Add residual connection, layer normalization and droput to the out tensor
    optionally according to the value of process_cmd.
    This will be used before or after multi-head attention and position-wise
    feed-forward networks.
    """
    for cmd in process_cmd:
        if cmd == "a":  # add residual connection
            out = out + prev_out if prev_out else out
        elif cmd == "n":  # add layer normalization
            out_type = out.dtype
            if out_type == fluid.core.VarDesc.VarType.FP16:
                out = layers.cast(x=out, dtype="float32")
            out = layers.layer_norm(
                out,
                begin_norm_axis=len(out.shape) - 1,
                param_attr=fluid.ParamAttr(
                    name=name + '_layer_norm_scale',
                    initializer=fluid.initializer.Constant(1.)),
                bias_attr=fluid.ParamAttr(
                    name=name + '_layer_norm_bias',
                    initializer=fluid.initializer.Constant(0.)))
            if out_type == fluid.core.VarDesc.VarType.FP16:
                out = layers.cast(x=out, dtype="float16")
        elif cmd == "d":  # add dropout
            if dropout_rate:
                out = layers.dropout(
                    out,
                    dropout_prob=dropout_rate,
                    dropout_implementation="upscale_in_train",
                    is_test=False)
    return out


def multi_head_attention(queries,
                         keys,
                         values,
                         attention_bias,
                         key_size,
                         value_size,
                         hidden_size,
                         n_head=1,
                         dropout_rate=0.,
                         cache=None,
                         param_initializer=None,
                         name='multi_head_att'):
    """
    Multi-Head Attention. Note that attn_bias is added to the logit before
    computing softmax activiation to mask certain selected positions so that
    they will not considered in attention weights.
    """
    keys = queries if keys is None else keys
    values = keys if values is None else values

    if not (len(queries.shape) == len(keys.shape) == len(values.shape) == 3):
        raise ValueError(
            "Inputs: quries, keys and values should all be 3-D tensors.")

    def __compute_qkv(queries, keys, values, n_head, key_size, value_size):
        """
        Add linear projection to queries, keys, and values.
        """
        q = layers.fc(input=queries,
                      size=key_size * n_head,
                      num_flatten_dims=2,
                      param_attr=fluid.ParamAttr(
                          name=name + '_query_fc.w_0',
                          initializer=param_initializer),
                      bias_attr=name + '_query_fc.b_0')
        k = layers.fc(input=keys,
                      size=key_size * n_head,
                      num_flatten_dims=2,
                      param_attr=fluid.ParamAttr(
                          name=name + '_key_fc.w_0',
                          initializer=param_initializer),
                      bias_attr=name + '_key_fc.b_0')
        v = layers.fc(input=values,
                      size=value_size * n_head,
                      num_flatten_dims=2,
                      param_attr=fluid.ParamAttr(
                          name=name + '_value_fc.w_0',
                          initializer=param_initializer),
                      bias_attr=name + '_value_fc.b_0')
        return q, k, v

    def __split_heads(x, num_head):
        """
        Reshape the last dimension of inpunt tensor x so that it becomes two
        dimensions and then transpose. Specifically, input a tensor with shape
        [bs, max_sequence_length, n_head * hidden_dim] then output a tensor
        with shape [bs, n_head, max_sequence_length, hidden_dim].
        """
        hidden_size = x.shape[-1]
        # The value 0 in shape attr means copying the corresponding dimension
        # size of the input as the output dimension size.
        reshaped = layers.reshape(
            x=x, shape=[0, 0, num_head, hidden_size // num_head], inplace=True)

        # permuate the dimensions into:
        # [batch_size, n_head, max_sequence_len, hidden_size_per_head]
        return layers.transpose(x=reshaped, perm=[0, 2, 1, 3])

    def __combine_heads(x):
        """
        Transpose and then reshape the last two dimensions of inpunt tensor x
        so that it becomes one dimension, which is reverse to __split_heads.
        """
        if len(x.shape) == 3: return x
        if len(x.shape) != 4:
            raise ValueError("Input(x) should be a 4-D Tensor.")

        trans_x = layers.transpose(x, perm=[0, 2, 1, 3])
        # The value 0 in shape attr means copying the corresponding dimension
        # size of the input as the output dimension size.
        return layers.reshape(
            x=trans_x,
            shape=[0, 0, trans_x.shape[2] * trans_x.shape[3]],
            inplace=True)

    def scaled_dot_product_attention(q, k, v, attn_bias, d_key, dropout_rate):
        """
        Scaled Dot-Product Attention
        """
        scaled_q = layers.scale(x=q, scale=d_key**-0.5)
        product = layers.matmul(x=scaled_q, y=k, transpose_y=True)
        if attn_bias:
            product += attn_bias
        weights = layers.softmax(product)
        if dropout_rate:
            weights = layers.dropout(
                weights,
                dropout_prob=dropout_rate,
                dropout_implementation="upscale_in_train",
                is_test=False)
        out = layers.matmul(weights, v)
        return out

    q, k, v = __compute_qkv(queries, keys, values, n_head, key_size, value_size)

    if cache is not None:  # use cache and concat time steps
        # Since the inplace reshape in __split_heads changes the shape of k and
        # v, which is the cache input for next time step, reshape the cache
        # input from the previous time step first.
        k = cache["k"] = layers.concat(
            [layers.reshape(
                cache["k"], shape=[0, 0, hidden_size]), k], axis=1)
        v = cache["v"] = layers.concat(
            [layers.reshape(
                cache["v"], shape=[0, 0, hidden_size]), v], axis=1)

    q = __split_heads(q, n_head)
    k = __split_heads(k, n_head)
    v = __split_heads(v, n_head)

    ctx_multiheads = scaled_dot_product_attention(q, k, v, attention_bias, key_size,
                                                  dropout_rate)

    out = __combine_heads(ctx_multiheads)

    # Project back to the model size.
    proj_out = layers.fc(input=out,
                         size=hidden_size,
                         num_flatten_dims=2,
                         param_attr=fluid.ParamAttr(
                             name=name + '_output_fc.w_0',
                             initializer=param_initializer),
                         bias_attr=name + '_output_fc.b_0')
    return proj_out

"""
def pre_process_layer(out, process_cmd, dropout_rate=0.,
                           name=''):
    pre_post_process_layer(None, out, process_cmd, dropout_rate, name)
"""
pre_process_layer = partial(pre_post_process_layer, None)

post_process_layer = pre_post_process_layer