# app/optimize.py

import numpy as np
from scipy.optimize import curve_fit

def model_func(x, a, b, c):
    """
    Примерен нелинеен модел: a * exp(b * x) + c
    """
    return a * np.exp(b * x) + c

def run_optimization(params):
    """
    Прави нелинейна регресия (curve_fit) на model_func спрямо данните в params.

    Очаква params да е dict с ключове:
      - 'x': списък или масив на x-стойности
      - 'y': списък или масив на y-стойности
      - (по избор) 'initial_guess': начално приближение [a0, b0, c0]

    Връща dict с:
      - 'optimal_parameters': списък [a, b, c]
      - 'covariance': матрица на ковариации
    """
    # Преобразуваме входа в numpy масиви
    x = np.array(params['x'], dtype=float)
    y = np.array(params['y'], dtype=float)

    # Начално приближение
    p0 = params.get('initial_guess', [1.0, 0.1, 0.0])

    # Извършваме нелинейната регресия
    popt, pcov = curve_fit(model_func, x, y, p0=p0)

    # Връщаме резултата като Python структури
    return {
        'optimal_parameters': popt.tolist(),
        'covariance': pcov.tolist()
    }
