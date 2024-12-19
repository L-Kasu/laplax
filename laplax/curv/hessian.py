"""Full hessian estimation."""

from functools import partial

import jax

from laplax.types import Callable, Data, LossFn, ModelFn, Params


def hvp(func, primals, tangents):
    return jax.jvp(jax.grad(func), (primals,), (tangents,))[1]


def concatenate_model_and_loss_fn(
    model_fn: ModelFn,
    loss_fn: LossFn | Callable | None = None,
    *,
    has_batch: bool = False,
) -> ModelFn:
    if has_batch:

        def model_fn(params, input):
            return jax.vmap(model_fn, in_axes=(None, 0))(params, input)

    if loss_fn == LossFn.MSE:
        return lambda params, input, target: jax.lax.l2_loss(
            model_fn(input=input, params=params) - target
        )
    if loss_fn == LossFn.CROSSENTROPY:
        return lambda params, input, target: jax.lax.l1_loss(
            model_fn(input=input, params=params) - target
        )
    if isinstance(loss_fn, Callable):
        return lambda params, input, target: loss_fn(
            model_fn(input=input, params=params), target
        )
    msg = f"Unknown loss function: {loss_fn}."
    raise ValueError(msg)


def create_hessian_mv_without_data(
    model_fn: ModelFn,
    params: Params,
    loss_fn: LossFn | Callable | None = None,
    *,
    has_batch: bool = False,
    **kwargs,
) -> Callable[[Params, Data], Params]:
    """Hessian-vector product without hardcoded data batch."""
    del kwargs
    if loss_fn is not None:
        model_fn = concatenate_model_and_loss_fn(model_fn, loss_fn, has_batch=has_batch)
    else:

        def model_fn(params, input, target):
            del target
            return model_fn(params, input)

    def _hessian_mv(vector: Params, data: Data) -> Params:
        return hvp(
            lambda p: model_fn(params=p, input=data["input"], target=data["target"]),
            params,
            vector,
        )

    return _hessian_mv


def create_hessian_mv(
    model_fn: ModelFn,
    params: Params,
    data: Data,
    loss_fn: LossFn | Callable | None = None,
    **kwargs,
) -> Callable[[Params], Params]:
    hessian_mv = create_hessian_mv_without_data(model_fn, params, loss_fn, **kwargs)
    return partial(hessian_mv, data=data)
