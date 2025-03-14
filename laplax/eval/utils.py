"""Pushforward utilities for evaluating probabilistic predictions on datasets.

This module provides utilities for evaluating probabilistic models on datasets and
managing metric computations.

Key features include:
- Wrapping functions to store outputs in a structured format.
- Finalizing multiple functions and collecting results in a dictionary.
- Applying prediction functions across datasets to generate predictions and evaluating
  them against their targets.
- Computing and transforming evaluation metrics for datasets using custom or default
  metrics.

These utilities streamline dataset evaluation workflows and ensure flexibility in metric
computation and result aggregation.
"""

import jax

from laplax.types import Any, Array, Callable, Data, InputArray
from laplax.util.utils import identity


def named_finalize_fn_wrapper(
    fn: Callable,
) -> Callable:
    """Wrap a function to store its result in a dictionary.

    This wrapper allows a function to be executed with specified arguments, and
    its output is stored in the `results` dictionary under a specified name.

    Args:
        fn: A callable function to be wrapped.

    Returns:
        Callable: A wrapped function that takes `results`, `aux`, `name`, and
        other keyword arguments, and updates the `results` dictionary.
    """

    def wrapper(
        results: dict[str, Array], aux: dict[str, Any] | None, name: str, **kwargs
    ):
        results[name] = fn(**kwargs)
        return results, aux

    return wrapper


def named_finalize_fns(
    fns: dict[str, Callable],
    results: dict,  # Typing must allow empty dict for initializations
    aux: dict[str, Any] | None = None,
    **kwargs,
) -> dict:
    """Execute a set of named functions and store their results in a dictionary.

    This function iterates over a dictionary of functions, executes each
    function with the provided keyword arguments, and updates the `results`
    dictionary with their outputs. The functions need to know what key to update the
    `results` dict with, which is given by their name in the `functions` dict.

    Args:
        fns: A dictionary where keys are names for the results, and values
            are callables to execute.
        results: A dictionary to store the outputs of the functions.
        aux: Auxiliary data passed to the functions.
        **kwargs: Additional arguments passed to each function.

    Returns:
        The updated `results` dictionary containing the outputs of all
        executed functions.
    """
    for name, func in fns.items():
        results, aux = func(results=results, aux=aux, name=name, **kwargs)
    return results


def finalize_fns(
    fns: list[Callable],
    results: dict,  # Typing must allow empty dict for initializations
    aux: dict[str, Any] | None = None,
    **kwargs,
) -> dict:
    """Execute a set of functions and store their results in a dictionary.

    This function iterates over a list of functions, executes each
    function with the provided keyword arguments, and updates the `results`
    dictionary with their outputs. The functions know what key they should update the
    results dict with.

    Args:
        fns: A list of callables to execute.
        results: A dictionary to store the outputs of the functions.
        aux: Auxiliary data passed to the functions.
        **kwargs: Additional arguments passed to each function.

    Returns:
        The updated `results` dictionary containing the outputs of all
        executed functions.
    """
    for func in fns:
        results, aux = func(results=results, aux=aux, **kwargs)
    return results


def evaluate_on_dataset(
    pred_fn: Callable[[InputArray], dict[str, Array]], data: Data, **kwargs
) -> dict:
    """Evaluate a prediction function on a dataset.

    This function applies a probabilistic predictive function (`pred_fn`) to
    each data point in the dataset, combining the predictions with the target
    labels.

    Args:
        pred_fn: A callable that takes an input array and returns predictions
            as a dictionary.
        data: A dataset, where each data point is a dictionary containing
            "input" and "target".
        **kwargs: Additional arguments, including:
            - `evaluate_on_dataset_batch_size`: Batch size for processing data
              (default: `data_batch_size`).

    Returns:
        A dictionary containing predictions and target labels for the entire dataset.
    """

    def evaluate_data_point(dp: Data) -> dict[str, Array]:
        return {**pred_fn(dp["input"]), "target": dp["target"]}

    return jax.lax.map(
        evaluate_data_point,
        data,
        batch_size=kwargs.get(
            "evaluate_on_dataset_batch_size", kwargs.get("data_batch_size")
        ),
    )


def evaluate_metrics_on_dataset(
    pred_fn: Callable[[InputArray], dict[str, Array]],
    data: Data,
    *,
    metrics: dict[str, Callable],
    apply: Callable = identity,
    **kwargs,
) -> dict:
    """Evaluate a set of metrics on a dataset.

    This function computes specified metrics for predictions generated by a
    probabilistic predictive function (`pred_fn`) over a dataset. The results
    can optionally be transformed using an `apply` function.

    Args:
        pred_fn: A callable that takes an input array and returns predictions
            as a dictionary.
        data: A dataset, where each data point is a dictionary containing
            "input" and "target".
        metrics: A dictionary of metrics to compute, where keys are metric
            names and values are callables.
        apply: A callable to transform the evaluated metrics (default: identity).
        **kwargs: Additional arguments, including:
            - `evaluate_metrics_on_dataset_batch_size`: Batch size for processing data
              (default: `data_batch_size`).

    Returns:
        dict: A dictionary containing the evaluated metrics for the entire
        dataset.
    """
    # Wrap metrics
    metrics = {name: named_finalize_fn_wrapper(fn) for name, fn in metrics.items()}

    # Setup pointwise evaluation
    def evaluate_data_point(dp: Data) -> dict[str, Array]:
        pred = {**pred_fn(dp["input"]), "target": dp["target"]}
        return named_finalize_fns(fns=metrics, results={}, aux=None, **pred)

    # Evaluate metrics
    evaluated_metrics = jax.lax.map(
        evaluate_data_point,
        data,
        batch_size=kwargs.get(
            "evaluate_metrics_on_dataset_batch_size", kwargs.get("data_batch_size")
        ),
    )
    return {metric: apply(evaluated_metrics[metric]) for metric in evaluated_metrics}
