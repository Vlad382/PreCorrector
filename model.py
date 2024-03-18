from typing import Callable

from jax import random, vmap
import jax.numpy as jnp
import jax.tree_util as tree
import jax.nn as jnn

from jax.ops import segment_sum
import equinox as eqx

from utils import graph_to_low_tri_mat
from data import bi_direc_edge_avg

class PrecNet(eqx.Module):
    NodeEncoder: eqx.Module
    EdgeEncoder: eqx.Module
    MessagePass: eqx.Module
    EdgeDecoder: eqx.Module

    def __init__(self, NodeEncoder, EdgeEncoder, MessagePass, EdgeDecoder):
        super(PrecNet, self).__init__()
        self.NodeEncoder = NodeEncoder
        self.EdgeEncoder = EdgeEncoder
        self.MessagePass = MessagePass
        self.EdgeDecoder = EdgeDecoder
        return
    
    def __call__(self, nodes, edges, receivers, senders, bi_edges_indx):
        nodes = self.NodeEncoder(nodes[None, ...])
        edges = self.EdgeEncoder(edges[None, ...])
        nodes, edges, receivers, senders = self.MessagePass(nodes, edges, receivers, senders)
        edges = bi_direc_edge_avg(edges, bi_edges_indx)
        edges = self.EdgeDecoder(edges)
        low_tri = graph_to_low_tri_mat(nodes, jnp.squeeze(edges), receivers, senders)
        return low_tri
    
    
class FullyConnectedNet(eqx.Module):
    layers: list
    act: Callable = eqx.field(static=True)
        
    def __init__(self, features, N_layers, key, act=jnn.relu):
        super(FullyConnectedNet, self).__init__()
        N_in, N_pr, N_out = features
        keys = random.split(key, N_layers)
        Ns = [N_in,] + [N_pr,] * (N_layers - 1) + [N_out,]
        self.layers = [eqx.nn.Conv1d(in_channels=N_in, out_channels=N_out, kernel_size=1, key=key) for N_in, N_out, key in zip(Ns[:-1], Ns[1:], keys)]
        self.act = act
        return
    
    def __call__(self, x):
        for l in self.layers[:-1]:
            x = l(x)
            x = self.act(x)
        x = self.layers[-1](x)
        return x
    
class MessagePassing(eqx.Module):
    update_edge_fn: eqx.Module
    update_node_fn: eqx.Module
    aggregate_edges_for_nodes_fn: Callable = eqx.field(static=True)
    mp_rounds: int = eqx.field(static=True)
        
    def __init__(self, update_edge_fn, update_node_fn, mp_rounds,
                aggregate_edges_for_nodes_fn=segment_sum):
        super(MessagePassing, self).__init__()
        self.update_edge_fn = update_edge_fn
        self.update_node_fn = update_node_fn
        self.aggregate_edges_for_nodes_fn = aggregate_edges_for_nodes_fn
        self.mp_rounds = mp_rounds
        return        
        
    def __call__(self, nodes, edges, receivers, senders):
        for _ in range(self.mp_rounds):
            nodes = self._update_nodes(nodes, edges, receivers, senders)
            edges = self._update_edges(nodes, edges, receivers, senders)
        return nodes, edges, receivers, senders
    
    # CHECK
    def _update_nodes(self, nodes, edges, receivers, senders):
        sum_n_node = tree.tree_leaves(nodes)[0].shape[1]
#         sent_attributes = tree.tree_map(lambda e: self.aggregate_edges_for_nodes_fn(e, senders, sum_n_node), jnp.einsum('ij->ji', edges))
#         sent_attributes = jnp.einsum('ij->ji', sent_attributes)
#         sent_attributes = vmap(tree.tree_map(lambda e: self.aggregate_edges_for_nodes_fn(e, senders, sum_n_node)),
#                                in_axes=(0), out_axes=(0))(edges)
        sent_attributes = vmap(
            tree.tree_map, 
            in_axes=(None, 0), out_axes=(0)
        )(lambda e: self.aggregate_edges_for_nodes_fn(e, senders, sum_n_node), edges)
    
#         received_attributes = tree.tree_map(lambda e: self.aggregate_edges_for_nodes_fn(e, receivers, sum_n_node), jnp.einsum('ij->ji', edges))
#         received_attributes = jnp.einsum('ij->ji', received_attributes)
        received_attributes = vmap(
            tree.tree_map, 
            in_axes=(None, 0), out_axes=(0)
        )(lambda e: self.aggregate_edges_for_nodes_fn(e, receivers, sum_n_node), edges)
        
        nodes = self.update_node_fn(jnp.concatenate([nodes, sent_attributes, received_attributes], axis=0))
        return nodes
    
    def _update_edges(self, nodes, edges, receivers, senders):
        sent_attributes = tree.tree_map(lambda n: n[:, senders], nodes)
        received_attributes = tree.tree_map(lambda n: n[:, receivers], nodes)

        # Find non-main-diagonal edges
        non_diag_edge_idx = jnp.nonzero(jnp.diff(jnp.hstack([senders[:, None], receivers[:, None]])), size=senders.shape[0]-nodes.shape[1], fill_value=jnp.nan)[0].astype(jnp.int32)

        feat_in = jnp.concatenate([
            edges[:, non_diag_edge_idx],
            sent_attributes[:, non_diag_edge_idx],
            received_attributes[:, non_diag_edge_idx]
        ], axis=0)
        edges_upd = self.update_edge_fn(feat_in)
        edges = edges.at[:, non_diag_edge_idx].set(edges_upd)
        return edges