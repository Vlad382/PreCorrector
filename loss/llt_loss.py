import jax.numpy as jnp
from jax import vmap
from jax.experimental import sparse as jsparse
from functools import partial

from linsolve.cg import ConjGrad
from linsolve.precond import llt_prec_trig_solve
from data.graph_utils import direc_graph_from_linear_system_sparse
from utils import asses_cond_with_res


import jax.numpy as jnp
from jax import vmap
from jax.experimental import sparse as jsparse
from functools import partial

from linsolve.cg import ConjGrad
from linsolve.precond import llt_prec_trig_solve
from data.graph_utils import direc_graph_from_linear_system_sparse
from utils import asses_cond_with_res

@jsparse.sparsify
def llt_loss(L, x, b):
    "L should be sparse (and not batched since function is vmaped)"
    return jnp.square(jnp.linalg.norm(L @ (L.T @ x) - b, ord=2))

def compute_loss_llt(model, X, y, reduction=jnp.mean):
    '''Placeholder for supervised learning `y`.
       Positions in `X`:
         X[0] - lhs A (for cond calc).
         X[1] - padded lhs A (for training).
         X[2] - rhs b.
         X[3] - indices of bi-directional edges in the graph.
         X[4] - solution of linear system x.
     '''
#     rhs_placeholder = jnp.ones_like(X[2])
    nodes, edges, receivers, senders, _ = direc_graph_from_linear_system_sparse(X[1], X[2])#rhs_placeholder)
    lhs_nodes, lhs_edges, lhs_receivers, lhs_senders, _ = direc_graph_from_linear_system_sparse(X[0], X[2])#rhs_placeholder)
    L = vmap(model, in_axes=((0, 0, 0, 0), 0), out_axes=(0))((nodes, edges, receivers, senders), X[3])#, (lhs_nodes, lhs_edges, lhs_receivers, lhs_senders))
    loss = vmap(llt_loss, in_axes=(0, 0, 0), out_axes=(0))(L, X[4], X[2])
    return reduction(loss)

def compute_loss_llt_with_cond(model, X, y, repeat_step, reduction=jnp.mean):
    '''Argument `repeat_step` is for ignoring duplicating lhs and rhs when Krylov dataset is used.'''
    nodes, edges, receivers, senders, _ = direc_graph_from_linear_system_sparse(X[1], X[2])
    lhs_nodes, lhs_edges, lhs_receivers, lhs_senders, _ = direc_graph_from_linear_system_sparse(X[0], X[2])
    L = vmap(model, in_axes=((0, 0, 0, 0), 0), out_axes=(0))((nodes, edges, receivers, senders), X[3])#, (lhs_nodes, lhs_edges, lhs_receivers, lhs_senders))
    loss = vmap(llt_loss, in_axes=(0, 0, 0), out_axes=(0))(L, X[4], X[2])
    
    cg = partial(ConjGrad, prec_func=partial(llt_prec_trig_solve, L=L[::repeat_step, ...]))
    cond_approx = asses_cond_with_res(X[0][::repeat_step, ...], X[2][::repeat_step, ...], cg)
    return reduction(loss), cond_approx

# @jsparse.sparsify
# def llt_loss(L, x, b):
#     "L should be sparse (and not batched since function is vmaped)"
#     return jnp.square(jnp.linalg.norm(L @ (L.T @ x) - b, ord=2))

# def compute_loss_llt(model, X, y, reduction=jnp.mean):
#     '''Placeholder for supervised learning `y`.
#        Positions in `X`:
#          X[0] - padded lhs A (for training).
#          X[1] - rhs b.
#          X[2] - solution of linear system x.
#      '''
#     nodes, edges, receivers, senders, _ = direc_graph_from_linear_system_sparse(X[0], X[1])
#     L = vmap(model, in_axes=(0), out_axes=(0))((nodes, edges, receivers, senders))#, X[3])#, (lhs_nodes, lhs_edges, lhs_receivers, lhs_senders))
#     loss = vmap(llt_loss, in_axes=(0, 0, 0), out_axes=(0))(L, X[2], X[1])
#     return reduction(loss)

# def compute_loss_llt_with_cond(model, X, y, repeat_step, reduction=jnp.mean):
#     '''Argument `repeat_step` is for ignoring duplicating lhs and rhs when Krylov dataset is used.'''
#     nodes, edges, receivers, senders, _ = direc_graph_from_linear_system_sparse(X[1], X[2])
#     lhs_nodes, lhs_edges, lhs_receivers, lhs_senders, _ = direc_graph_from_linear_system_sparse(X[0], X[2])
# #     L = vmap(model, in_axes=((0, 0, 0, 0), 0, (0, 0, 0, 0)), out_axes=(0))((nodes, edges, receivers, senders), X[3], (lhs_nodes, lhs_edges, lhs_receivers, lhs_senders))
#     L = vmap(model, in_axes=((0, 0, 0, 0), 0), out_axes=(0))((nodes, edges, receivers, senders), X[3])#, (lhs_nodes, lhs_edges, lhs_receivers, lhs_senders))
#     loss = vmap(llt_loss, in_axes=(0, 0, 0), out_axes=(0))(L, X[4], X[2])
    
#     cg = partial(ConjGrad, prec_func=partial(llt_prec_trig_solve, L=L[::repeat_step, ...]))
#     cond_approx = asses_cond_with_res(X[0][::repeat_step, ...], X[2][::repeat_step, ...], cg)
#     return reduction(loss), cond_approx
