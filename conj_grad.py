import jax.numpy as jnp
from jax import random, vmap, scipy as jscipy
from jax.experimental import sparse as jsparse
from jax.lax import scan

def apply_Jacobi(model, res, nodes, edges, receivers, senders, bi_edges_indx, A):
    # TODO
    diags = vmap(jnp.diag, in_axes=(0), out_axes=(0))(A.todense())
    inv_diags = vmap(lambda X: 1./X, in_axes=(0), out_axes=(0))(diags)
    P_inv = vmap(jnp.diag, in_axes=(0), out_axes=(0))(inv_diags)
    omega = vmap(lambda P_inv, res: P_inv @ res, in_axes=(0, 0), out_axes=(0))(P_inv, res)
    return omega

def apply_LDLT(res, L, D, *args):
    # TODO
    y, _ = vmap(jscipy.sparse.linalg.bicgstab, in_axes=(0), out_axes=(0))(L, res)
    L_T = jsparse.bcoo_transpose(L, permutation=[0, 2, 1])
    DL_T = vmap(jsparse.sparsify(lambda A, B: A @ B), in_axes=(0, 0), out_axes=(0))(D, L_T)
    omega, _ = vmap(jscipy.sparse.linalg.bicgstab, in_axes=(0), out_axes=(0))(DL_T, y)
    return omega

def apply_LLT(res, L, *args):
    y, _ = vmap(jscipy.sparse.linalg.bicgstab, in_axes=(0), out_axes=(0))(L, res)
    omega, _ = vmap(jscipy.sparse.linalg.bicgstab, in_axes=(0), out_axes=(0))(jsparse.bcoo_transpose(L, permutation=[0, 2, 1]), y)
    return omega

def ConjGrad(A, rhs, N_iter, prec_func=None, eps=1e-30, seed=42):
    '''Preconditioned Conjuagte Gradient function'''
    apply_prec = prec_func if prec_func else lambda res, *args: res
    samples = rhs.shape[0]
    n = rhs.shape[1]

    X = random.normal(random.PRNGKey(seed), [samples, n])
    R = jnp.zeros([samples, n, N_iter+1])
    Z = jnp.zeros([samples, n])
    P = jnp.zeros([samples, n])

    R = R.at[:, :, 0].set(rhs - jsparse.bcoo_dot_general(A, X, dimension_numbers=((2,1), (0,0))))
    Z = apply_prec(res=R[:, :, 0])
    P = Z

    w = jsparse.bcoo_dot_general(A, P, dimension_numbers=((2,1), (0,0)))
    alpha = jnp.einsum('bj, bj -> b', Z, R[:, :, 0]) / (jnp.einsum('bj, bj -> b', w, P) + eps)
    X = X + jnp.einsum('bj, b -> bj', P, alpha)
    R = R.at[:, :, 1].set(R[:, :, 0] - jnp.einsum('bj, b -> bj', w, alpha))
    
    def cg_body(carry, idx):
        X, R, Z, P = carry

        z_k_plus_1 = apply_prec(res=R[:, :, idx])

        beta = jnp.einsum('bj, bj->b', R[:, :, idx], z_k_plus_1) / (jnp.einsum('bj, bj->b', R[:, :, idx-1], Z) + eps)
        Z = z_k_plus_1
        P = Z + jnp.einsum('b, bj->bj', beta, P)

        w = jsparse.bcoo_dot_general(A, P, dimension_numbers=((2,1), (0,0)))
        alpha = jnp.einsum('bj, bj -> b', Z, R[:, :, idx]) / (jnp.einsum('bj, bj -> b', P, w) + eps)

        X = X + jnp.einsum('b, bj->bj', alpha, P)
        R = R.at[:, :, idx+1].set(R[:, :, idx] - jnp.einsum('b, bj->bj', alpha, w))

        carry = (X, R, Z, P)
        return carry, None

    carry_init = (X, R, Z, P)        
    (X, R, _, _), _ = scan(cg_body, carry_init, jnp.arange(1, N_iter))
    return X, R