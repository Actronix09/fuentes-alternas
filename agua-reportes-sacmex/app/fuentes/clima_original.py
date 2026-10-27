"""Fuente del programa original: clima diario de Open-Meteo, 1er semestre de 2019.

Es el CSV que el DW original carga en staging_clima; se conserva sin modificar
y no se descarga de nuevo. Archivo: datos/original/clima/clima_original_2019.csv
"""
import csv

from comun import DIR_DATOS

DIRECTORIO = DIR_DATOS / 'original' / 'clima'
ARCHIVO = DIRECTORIO / 'clima_original_2019.csv'


if __name__ == '__main__':
    with ARCHIVO.open(encoding='utf-8-sig', newline='') as f:
        print(f'{sum(1 for _ in csv.reader(f)) - 1} registros de clima del programa original')
