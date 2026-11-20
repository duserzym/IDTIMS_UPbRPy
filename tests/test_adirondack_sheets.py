"""Private, in-place legacy regressions; no workbook measurements are stored here.

Known failures are strict expectations: both a new mismatch and a resolved one
fail so a reviewer must update the cause classification after an engine fix.
"""
from collections import Counter
import importlib.util
import os
from pathlib import Path

import pytest


# source, cause class, cause, quantities, affected raw-column/fraction IDs.
# Each entry explicitly describes a set of known failing live comparisons.
EXPECTED_FAILURES = {
    'MA1_zircon_UPbR21XML.xls': [
        ('csv', 'd', 'joint_covariance',
         ('rho_7568_r',),
         ('I:z5',)),
        ('csv', 'e', 'export_settings',
         ('Pbc_export', 'Pbr_Pbc', 'R68r_Th_error_pct_2s', 'R75r_error_pct_2s', 'R76r_Th', 'R76r_Th_error_pct_2s', 'R86rad', 'Th_U', 't68_Th_corr_std', 't75_std', 't76_Th_corr_std'),
         ('E:z1', 'F:z2', 'G:z3', 'H:z4', 'I:z5', 'J:z6', 'K:z7', 'L:z8', 'N:z9b', 'O:z10a', 'P:z10b')),
        ('csv', 'e', 'export_settings',
         ('Pb206r_scaled', 'R68r_Th', 'R75r', 'rho_7568_r', 't68_Th_corr', 't75', 't76_Th_corr'),
         ('E:z1', 'F:z2', 'G:z3', 'H:z4', 'J:z6', 'K:z7', 'L:z8', 'N:z9b', 'O:z10a', 'P:z10b')),
        ('csv', 'e', 'export_settings',
         ('R64fc',),
         ('E:z1', 'F:z2', 'H:z4', 'K:z7', 'L:z8', 'N:z9b', 'O:z10a', 'P:z10b')),
        ('csv', 'e', 'export_settings',
         ('mol_fraction_206r',),
         ('E:z1', 'G:z3', 'J:z6', 'L:z8', 'N:z9b', 'O:z10a')),
        ('engine', 'c', 'sheet_208_quotient',
         ('Pb_R84m_std',),
         ('E:z1', 'F:z2', 'G:z3', 'H:z4', 'I:z5', 'J:z6', 'K:z7', 'L:z8', 'M:z9a', 'N:z9b', 'O:z10a', 'P:z10b')),
        ('engine', 'c', 'sheet_U_derivative',
         ('R86s_error_pct_2s', 'rho_8676_s'),
         ('G:z3', 'H:z4', 'I:z5', 'J:z6', 'K:z7', 'O:z10a')),
        ('engine', 'c', 'sheet_zero_initial_error',
         ('R54s_error_pct_2s',),
         ('E:z1', 'F:z2', 'G:z3', 'H:z4', 'I:z5', 'J:z6', 'K:z7', 'L:z8', 'M:z9a', 'N:z9b', 'O:z10a', 'P:z10b')),
        ('engine', 'd', 'joint_covariance',
         ('Pb206r_std', 'Pb207r_std', 'Pb208r_std', 'R68r_Th_error_pct_2s', 'R68r_error_pct_2s', 'R75r_Th_error_pct_2s', 'R75r_error_pct_2s', 'R76r_Th_error_pct_2s', 'R76r_error_pct_2s', 'U235s_std', 'U238s_std', 'rho_7568_r', 'rho_8676_r', 't68_Th_corr_std', 't68_std', 't75_std', 't76_Th_corr_std', 't76_std'),
         ('E:z1', 'F:z2', 'G:z3', 'H:z4', 'I:z5', 'J:z6', 'K:z7', 'L:z8', 'M:z9a', 'N:z9b', 'O:z10a', 'P:z10b')),
        ('output_table', 'c', 'sheet_U_derivative',
         ('R86s_error_pct_2s', 'rho_8676_s'),
         ('G:z3', 'H:z4', 'I:z5', 'J:z6', 'K:z7', 'O:z10a')),
        ('output_table', 'c', 'sheet_zero_initial_error',
         ('R54s_error_pct_2s',),
         ('E:z1', 'F:z2', 'G:z3', 'H:z4', 'I:z5', 'J:z6', 'K:z7', 'L:z8', 'M:z9a', 'N:z9b', 'O:z10a', 'P:z10b')),
        ('output_table', 'd', 'joint_covariance',
         ('R68r_Th_error_pct_2s', 'R75r_error_pct_2s', 'R76r_Th_error_pct_2s', 'rho_7568_r', 't68_Th_corr_std', 't75_std', 't76_Th_corr_std'),
         ('E:z1', 'F:z2', 'G:z3', 'H:z4', 'I:z5', 'J:z6', 'K:z7', 'L:z8', 'M:z9a', 'N:z9b', 'O:z10a', 'P:z10b')),
        ('publication', 'd', 'joint_covariance',
         ('rho_7568_r',),
         ('I:z5',)),
        ('publication', 'e', 'export_settings',
         ('Pbc_export', 'Pbr_Pbc', 'Pbr_pg', 'R68r_Th_error_pct_2s', 'R75r_error_pct_2s', 'R76r_Th_error_pct_2s', 'R86rad', 'Th_U', 't68_Th_corr_std', 't75_std', 't76_Th_corr_std'),
         ('E:z1', 'F:z2', 'G:z3', 'H:z4', 'I:z5', 'J:z6', 'K:z7', 'L:z8', 'N:z9b', 'O:z10a', 'P:z10b')),
        ('publication', 'e', 'export_settings',
         ('Pb206r_scaled', 'R68r_Th', 'R75r', 'R76r_Th', 'rho_7568_r', 't68_Th_corr', 't75', 't76_Th_corr'),
         ('E:z1', 'F:z2', 'G:z3', 'H:z4', 'J:z6', 'K:z7', 'L:z8', 'N:z9b', 'O:z10a', 'P:z10b')),
        ('publication', 'e', 'export_settings',
         ('R64fc',),
         ('E:z1', 'F:z2', 'H:z4', 'K:z7', 'L:z8', 'N:z9b', 'O:z10a', 'P:z10b')),
        ('publication', 'e', 'export_settings',
         ('mol_fraction_206r',),
         ('E:z1', 'G:z3', 'J:z6', 'L:z8', 'N:z9b', 'O:z10a')),
    ],
    'MA1_apatite_UPbR21XML.xls': [
        ('csv', 'c', 'sheet_U_derivative',
         ('R86s_error_pct_2s', 'rho_8676_s'),
         ('M:a9',)),
        ('csv', 'c', 'sheet_common_mass',
         ('Pbc_export',),
         ('E:a1', 'F:a2', 'G:a3', 'H:a4', 'I:a5', 'J:a6', 'K:a7', 'L:a8', 'M:a9', 'N:a10', 'O:a11', 'P:a12', 'Q:a13')),
        ('csv', 'd', 'joint_covariance',
         ('R68r_Th_error_pct_2s', 'R75r_error_pct_2s', 'R76r_Th_error_pct_2s', 'rho_7568_r', 't68_Th_corr_std', 't75_std', 't76_Th_corr_std'),
         ('E:a1', 'F:a2', 'G:a3', 'H:a4', 'I:a5', 'J:a6', 'K:a7', 'L:a8', 'M:a9', 'N:a10', 'O:a11', 'P:a12', 'Q:a13')),
        ('engine', 'c', 'sheet_208_quotient',
         ('Pb_R84m_std',),
         ('E:a1', 'F:a2', 'G:a3', 'H:a4', 'I:a5', 'J:a6', 'K:a7', 'L:a8', 'M:a9', 'N:a10', 'O:a11', 'P:a12', 'Q:a13')),
        ('engine', 'c', 'sheet_U_derivative',
         ('R86s_error_pct_2s', 'rho_8646_s', 'rho_8676_s'),
         ('M:a9',)),
        ('engine', 'd', 'date_domain',
         ('FPb', 'FPb_std', 'FU', 'FU_std', 'Pb204b', 'Pb204c', 'Pb204c_std', 'Pb206b', 'Pb206c', 'Pb206r', 'Pb206r_std', 'Pb206s', 'Pb206s_std', 'Pb207b', 'Pb207c', 'Pb207r', 'Pb207r_std', 'Pb207s', 'Pb207s_std', 'Pb208b', 'Pb208c', 'Pb208r', 'Pb208r_std', 'Pb_R45m', 'Pb_R45m_error_pct_1s', 'Pb_R46m', 'Pb_R46m_error_pct_1s', 'Pb_R65m', 'Pb_R65m_error_pct_1s', 'Pb_R75m', 'Pb_R75m_error_pct_1s', 'Pb_R76m', 'Pb_R76m_error_pct_1s', 'Pb_R84m_std', 'Pb_R85m', 'Pb_R85m_error_pct_1s', 'Pb_ppm', 'Pbc_pg', 'Pbr_Pbc', 'Pbr_pg', 'R46s', 'R46s_error_pct_2s', 'R54s', 'R54s_error_pct_2s', 'R64fc', 'R64s', 'R64s_error_pct_2s', 'R68r', 'R68r_Th', 'R68r_Th_error_pct_2s', 'R68r_error_pct_2s', 'R74s', 'R74s_error_pct_2s', 'R75r', 'R75r_Th', 'R75r_Th_error_pct_2s', 'R75r_error_pct_2s', 'R76r', 'R76r_Th', 'R76r_Th_error_pct_2s', 'R76r_error_pct_2s', 'R76s', 'R76s_error_pct_2s', 'R84s', 'R84s_error_pct_2s', 'R86rad', 'R86s', 'R86s_error_pct_2s', 'Th232s', 'Th_U', 'Th_ppm', 'U235s', 'U235s_std', 'U238s', 'U238s_std', 'U_R35m', 'U_R35m_error_pct_1s', 'U_R83m', 'U_R83m_error_pct_1s', 'U_R85m', 'U_R85m_error_pct_1s', 'U_ppm', 'mol_fraction_206r', 'rho_7568_r', 'rho_7646_s', 'rho_8646_s', 'rho_8676_r', 'rho_8676_s', 't68', 't68_Th_corr', 't68_Th_corr_std', 't68_std', 't75', 't75_std', 't76', 't76_Th_corr', 't76_Th_corr_std', 't76_std'),
         ('Y:C13 TPB', 'Z:C14 TPB')),
        ('engine', 'd', 'joint_covariance',
         ('Pb206r_std', 'Pb207r_std', 'Pb208r_std', 'R68r_Th_error_pct_2s', 'R68r_error_pct_2s', 'R75r_Th_error_pct_2s', 'R75r_error_pct_2s', 'R76r_Th_error_pct_2s', 'R76r_error_pct_2s', 'U235s_std', 'U238s_std', 'rho_7568_r', 'rho_8676_r', 't68_Th_corr_std', 't68_std', 't75_std', 't76_Th_corr_std', 't76_std'),
         ('E:a1', 'F:a2', 'G:a3', 'H:a4', 'I:a5', 'J:a6', 'K:a7', 'L:a8', 'M:a9', 'N:a10', 'O:a11', 'P:a12', 'Q:a13')),
        ('engine', 'e', 'missing_measurement',
         ('FPb', 'FPb_std', 'FU', 'FU_std', 'Pb204b', 'Pb204c', 'Pb204c_std', 'Pb206b', 'Pb206c', 'Pb206r', 'Pb206r_std', 'Pb206s', 'Pb206s_std', 'Pb207b', 'Pb207c', 'Pb207r', 'Pb207r_std', 'Pb207s', 'Pb207s_std', 'Pb208b', 'Pb208c', 'Pb208r', 'Pb208r_std', 'Pb_R45m', 'Pb_R45m_error_pct_1s', 'Pb_R46m', 'Pb_R46m_error_pct_1s', 'Pb_R65m', 'Pb_R65m_error_pct_1s', 'Pb_R75m', 'Pb_R75m_error_pct_1s', 'Pb_R76m', 'Pb_R76m_error_pct_1s', 'Pb_R84m_std', 'Pb_R85m', 'Pb_R85m_error_pct_1s', 'Pb_ppm', 'Pbc_pg', 'Pbr_Pbc', 'Pbr_pg', 'R46s', 'R46s_error_pct_2s', 'R54s', 'R54s_error_pct_2s', 'R64fc', 'R64s', 'R64s_error_pct_2s', 'R68r', 'R68r_Th', 'R68r_Th_error_pct_2s', 'R68r_error_pct_2s', 'R74s', 'R74s_error_pct_2s', 'R75r', 'R75r_Th', 'R75r_Th_error_pct_2s', 'R75r_error_pct_2s', 'R76r', 'R76r_Th', 'R76r_Th_error_pct_2s', 'R76r_error_pct_2s', 'R76s', 'R76s_error_pct_2s', 'R84s', 'R84s_error_pct_2s', 'R86rad', 'R86s', 'R86s_error_pct_2s', 'Th232s', 'Th_U', 'Th_ppm', 'U235s', 'U235s_std', 'U238s', 'U238s_std', 'U_R35m', 'U_R35m_error_pct_1s', 'U_R83m', 'U_R83m_error_pct_1s', 'U_R85m', 'U_R85m_error_pct_1s', 'U_ppm', 'mol_fraction_206r', 'rho_7568_r', 'rho_7646_s', 'rho_8646_s', 'rho_8676_r', 'rho_8676_s', 't68', 't68_Th_corr', 't68_Th_corr_std', 't68_std', 't75', 't75_std', 't76', 't76_Th_corr', 't76_Th_corr_std', 't76_std'),
         ('AA:C15 TPB',)),
        ('output_table', 'c', 'sheet_U_derivative',
         ('R86s_error_pct_2s', 'rho_8646_s', 'rho_8676_s'),
         ('M:a9',)),
        ('output_table', 'c', 'sheet_common_mass',
         ('Pbc_export',),
         ('E:a1', 'F:a2', 'G:a3', 'H:a4', 'I:a5', 'J:a6', 'K:a7', 'L:a8', 'M:a9', 'N:a10', 'O:a11', 'P:a12', 'Q:a13')),
        ('output_table', 'd', 'date_domain',
         ('Pb206r_scaled', 'Pb_ppm', 'Pbc_export', 'Pbr_Pbc', 'R46s', 'R46s_error_pct_2s', 'R54s', 'R54s_error_pct_2s', 'R64fc', 'R64s', 'R64s_error_pct_2s', 'R68r_Th', 'R68r_Th_error_pct_2s', 'R74s', 'R74s_error_pct_2s', 'R75r', 'R75r_error_pct_2s', 'R76r_Th', 'R76r_Th_error_pct_2s', 'R76s', 'R76s_error_pct_2s', 'R84s', 'R84s_error_pct_2s', 'R86rad', 'R86s', 'R86s_error_pct_2s', 'Th_U', 'U_ppm', 'mol_fraction_206r', 'rho_5474_s', 'rho_7464_s', 'rho_7568_r', 'rho_7646_s', 'rho_8464_s', 'rho_8646_s', 'rho_8676_s', 't68_Th_corr', 't68_Th_corr_std', 't75', 't75_std', 't76_Th_corr', 't76_Th_corr_std'),
         ('Y:C13 TPB', 'Z:C14 TPB')),
        ('output_table', 'd', 'joint_covariance',
         ('R68r_Th_error_pct_2s', 'R75r_error_pct_2s', 'R76r_Th_error_pct_2s', 'rho_7568_r', 't68_Th_corr_std', 't75_std', 't76_Th_corr_std'),
         ('E:a1', 'F:a2', 'G:a3', 'H:a4', 'I:a5', 'J:a6', 'K:a7', 'L:a8', 'M:a9', 'N:a10', 'O:a11', 'P:a12', 'Q:a13')),
        ('output_table', 'e', 'missing_measurement',
         ('Pb206r_scaled', 'Pb_ppm', 'Pbc_export', 'Pbr_Pbc', 'R46s', 'R46s_error_pct_2s', 'R54s', 'R54s_error_pct_2s', 'R64fc', 'R64s', 'R64s_error_pct_2s', 'R68r_Th', 'R68r_Th_error_pct_2s', 'R74s', 'R74s_error_pct_2s', 'R75r', 'R75r_error_pct_2s', 'R76r_Th', 'R76r_Th_error_pct_2s', 'R76s', 'R76s_error_pct_2s', 'R84s', 'R84s_error_pct_2s', 'R86rad', 'R86s', 'R86s_error_pct_2s', 'Th_U', 'U_ppm', 'mol_fraction_206r', 'rho_5474_s', 'rho_7464_s', 'rho_7568_r', 'rho_7646_s', 'rho_8464_s', 'rho_8646_s', 'rho_8676_s', 't68_Th_corr', 't68_Th_corr_std', 't75', 't75_std', 't76_Th_corr', 't76_Th_corr_std'),
         ('AA:C15 TPB',)),
    ],
    'MA5_zircon_UPbR21XML.xls': [
        ('csv', 'd', 'joint_covariance',
         ('R68r_Th_error_pct_2s', 'R75r_error_pct_2s', 'R76r_Th_error_pct_2s', 'rho_7568_r', 't68_Th_corr_std', 't75_std', 't76_Th_corr_std'),
         ('E:z1', 'F:z2', 'G:z3', 'I:z5', 'J:z6', 'K:z7', 'L:z8', 'M:z9a')),
        ('engine', 'c', 'sheet_208_quotient',
         ('Pb_R84m_std',),
         ('E:z1', 'F:z2', 'G:z3', 'I:z5', 'J:z6', 'K:z7', 'L:z8', 'M:z9a')),
        ('engine', 'c', 'sheet_U_derivative',
         ('R86s_error_pct_2s', 'rho_8676_s'),
         ('F:z2', 'K:z7', 'M:z9a')),
        ('engine', 'c', 'sheet_zero_initial_error',
         ('R54s_error_pct_2s',),
         ('E:z1', 'F:z2', 'G:z3', 'I:z5', 'J:z6', 'K:z7', 'L:z8', 'M:z9a')),
        ('engine', 'd', 'joint_covariance',
         ('Pb206r_std', 'Pb207r_std', 'Pb208r_std', 'R68r_Th_error_pct_2s', 'R68r_error_pct_2s', 'R75r_Th_error_pct_2s', 'R75r_error_pct_2s', 'R76r_Th_error_pct_2s', 'R76r_error_pct_2s', 'U235s_std', 'U238s_std', 'rho_7568_r', 'rho_8676_r', 't68_Th_corr_std', 't68_std', 't75_std', 't76_Th_corr_std', 't76_std'),
         ('E:z1', 'F:z2', 'G:z3', 'I:z5', 'J:z6', 'K:z7', 'L:z8', 'M:z9a')),
        ('engine', 'e', 'missing_measurement',
         ('FPb', 'FPb_std', 'FU', 'FU_std', 'Pb204b', 'Pb204c', 'Pb204c_std', 'Pb206b', 'Pb206c', 'Pb206r', 'Pb206r_std', 'Pb206s', 'Pb206s_std', 'Pb207b', 'Pb207c', 'Pb207r', 'Pb207r_std', 'Pb207s', 'Pb207s_std', 'Pb208b', 'Pb208c', 'Pb208r', 'Pb208r_std', 'Pb_R45m', 'Pb_R45m_error_pct_1s', 'Pb_R46m', 'Pb_R46m_error_pct_1s', 'Pb_R65m', 'Pb_R65m_error_pct_1s', 'Pb_R75m', 'Pb_R75m_error_pct_1s', 'Pb_R76m', 'Pb_R76m_error_pct_1s', 'Pb_R84m_std', 'Pb_R85m', 'Pb_R85m_error_pct_1s', 'Pb_ppm', 'Pbc_pg', 'Pbr_Pbc', 'Pbr_pg', 'R46s', 'R46s_error_pct_2s', 'R54s', 'R54s_error_pct_2s', 'R64fc', 'R64s', 'R64s_error_pct_2s', 'R68r', 'R68r_Th', 'R68r_Th_error_pct_2s', 'R68r_error_pct_2s', 'R74s', 'R74s_error_pct_2s', 'R75r', 'R75r_Th', 'R75r_Th_error_pct_2s', 'R75r_error_pct_2s', 'R76r', 'R76r_Th', 'R76r_Th_error_pct_2s', 'R76r_error_pct_2s', 'R76s', 'R76s_error_pct_2s', 'R84s', 'R84s_error_pct_2s', 'R86rad', 'R86s', 'R86s_error_pct_2s', 'Th232s', 'Th_U', 'Th_ppm', 'U235s', 'U235s_std', 'U238s', 'U238s_std', 'U_R35m', 'U_R35m_error_pct_1s', 'U_R83m', 'U_R83m_error_pct_1s', 'U_R85m', 'U_R85m_error_pct_1s', 'U_ppm', 'mol_fraction_206r', 'rho_7568_r', 'rho_7646_s', 'rho_8646_s', 'rho_8676_r', 'rho_8676_s', 't68', 't68_Th_corr', 't68_Th_corr_std', 't68_std', 't75', 't75_std', 't76', 't76_Th_corr', 't76_Th_corr_std', 't76_std'),
         ('H:z4', 'N:z9b')),
        ('output_table', 'c', 'sheet_U_derivative',
         ('R86s_error_pct_2s', 'rho_8676_s'),
         ('F:z2', 'K:z7', 'M:z9a')),
        ('output_table', 'c', 'sheet_zero_initial_error',
         ('R54s_error_pct_2s',),
         ('E:z1', 'F:z2', 'G:z3', 'I:z5', 'J:z6', 'K:z7', 'L:z8', 'M:z9a')),
        ('output_table', 'd', 'joint_covariance',
         ('R68r_Th_error_pct_2s', 'R75r_error_pct_2s', 'R76r_Th_error_pct_2s', 'rho_7568_r', 't68_Th_corr_std', 't75_std', 't76_Th_corr_std'),
         ('E:z1', 'F:z2', 'G:z3', 'I:z5', 'J:z6', 'K:z7', 'L:z8', 'M:z9a')),
        ('output_table', 'e', 'missing_measurement',
         ('Pb206r_scaled', 'Pb_ppm', 'Pbc_export', 'Pbr_Pbc', 'R46s', 'R46s_error_pct_2s', 'R54s', 'R54s_error_pct_2s', 'R64fc', 'R64s', 'R64s_error_pct_2s', 'R68r_Th', 'R68r_Th_error_pct_2s', 'R74s', 'R74s_error_pct_2s', 'R75r', 'R75r_error_pct_2s', 'R76r_Th', 'R76r_Th_error_pct_2s', 'R76s', 'R76s_error_pct_2s', 'R84s', 'R84s_error_pct_2s', 'R86rad', 'R86s', 'R86s_error_pct_2s', 'Th_U', 'U_ppm', 'mol_fraction_206r', 'rho_5474_s', 'rho_7464_s', 'rho_7568_r', 'rho_7646_s', 'rho_8464_s', 'rho_8646_s', 'rho_8676_s', 't68_Th_corr', 't68_Th_corr_std', 't75', 't75_std', 't76_Th_corr', 't76_Th_corr_std'),
         ('H:z4',)),
        ('publication', 'd', 'joint_covariance',
         ('R68r_Th_error_pct_2s', 'R75r_error_pct_2s', 'R76r_Th_error_pct_2s', 'rho_7568_r', 't68_Th_corr_std', 't75_std', 't76_Th_corr_std'),
         ('E:z1', 'F:z2', 'G:z3', 'I:z5', 'J:z6', 'K:z7', 'L:z8', 'M:z9a')),
    ],
    'MA5_apatite_UPbR21XML.xls': [
        ('csv', 'c', 'sheet_U_derivative',
         ('R86s_error_pct_2s', 'rho_8676_s'),
         ('E:a1', 'K:a7', 'L:a8')),
        ('csv', 'e', 'export_settings',
         ('Pb206r_scaled', 'Pbc_export', 'Pbr_Pbc', 'R68r_Th', 'R68r_Th_error_pct_2s', 'R75r', 'R75r_error_pct_2s', 'R76r_Th', 'R76r_Th_error_pct_2s', 'R86rad', 'Th_U', 'mol_fraction_206r', 'rho_7568_r', 't68_Th_corr', 't68_Th_corr_std', 't75', 't75_std', 't76_Th_corr', 't76_Th_corr_std'),
         ('E:a1', 'F:a2', 'G:a3', 'H:a4', 'I:a5 - D', 'J:a6', 'K:a7', 'L:a8', 'M:a9', 'N:a10', 'O:a11', 'P:a12', 'R:a14')),
        ('engine', 'c', 'sheet_208_quotient',
         ('Pb_R84m_std',),
         ('E:a1', 'F:a2', 'G:a3', 'H:a4', 'I:a5 - D', 'J:a6', 'K:a7', 'L:a8', 'M:a9', 'N:a10', 'O:a11', 'P:a12', 'R:a14')),
        ('engine', 'c', 'sheet_U_derivative',
         ('R86s_error_pct_2s', 'rho_8646_s', 'rho_8676_s'),
         ('E:a1', 'K:a7', 'L:a8')),
        ('engine', 'd', 'date_domain',
         ('FPb', 'FPb_std', 'FU', 'FU_std', 'Pb204b', 'Pb204c', 'Pb204c_std', 'Pb206b', 'Pb206c', 'Pb206r', 'Pb206r_std', 'Pb206s', 'Pb206s_std', 'Pb207b', 'Pb207c', 'Pb207r', 'Pb207r_std', 'Pb207s', 'Pb207s_std', 'Pb208b', 'Pb208c', 'Pb208r', 'Pb208r_std', 'Pb_R45m', 'Pb_R45m_error_pct_1s', 'Pb_R46m', 'Pb_R46m_error_pct_1s', 'Pb_R65m', 'Pb_R65m_error_pct_1s', 'Pb_R75m', 'Pb_R75m_error_pct_1s', 'Pb_R76m', 'Pb_R76m_error_pct_1s', 'Pb_R84m_std', 'Pb_R85m', 'Pb_R85m_error_pct_1s', 'Pb_ppm', 'Pbc_pg', 'Pbr_Pbc', 'Pbr_pg', 'R46s', 'R46s_error_pct_2s', 'R54s', 'R54s_error_pct_2s', 'R64fc', 'R64s', 'R64s_error_pct_2s', 'R68r', 'R68r_Th', 'R68r_Th_error_pct_2s', 'R68r_error_pct_2s', 'R74s', 'R74s_error_pct_2s', 'R75r', 'R75r_Th', 'R75r_Th_error_pct_2s', 'R75r_error_pct_2s', 'R76r', 'R76r_Th', 'R76r_Th_error_pct_2s', 'R76r_error_pct_2s', 'R76s', 'R76s_error_pct_2s', 'R84s', 'R84s_error_pct_2s', 'R86rad', 'R86s', 'R86s_error_pct_2s', 'Th232s', 'Th_U', 'Th_ppm', 'U235s', 'U235s_std', 'U238s', 'U238s_std', 'U_R35m', 'U_R35m_error_pct_1s', 'U_R83m', 'U_R83m_error_pct_1s', 'U_R85m', 'U_R85m_error_pct_1s', 'U_ppm', 'mol_fraction_206r', 'rho_7568_r', 'rho_7646_s', 'rho_8646_s', 'rho_8676_r', 'rho_8676_s', 't68', 't68_Th_corr', 't68_Th_corr_std', 't68_std', 't75', 't75_std', 't76', 't76_Th_corr', 't76_Th_corr_std', 't76_std'),
         ('X:C13 TPB', 'Y:C14 TPB')),
        ('engine', 'd', 'joint_covariance',
         ('Pb207r_std', 'Pb208r_std', 'R68r_Th_error_pct_2s', 'R68r_error_pct_2s', 'R75r_Th_error_pct_2s', 'R75r_error_pct_2s', 'R76r_Th_error_pct_2s', 'R76r_error_pct_2s', 'U235s_std', 'U238s_std', 'rho_7568_r', 'rho_8676_r', 't68_Th_corr_std', 't68_std', 't75_std', 't76_Th_corr_std', 't76_std'),
         ('E:a1', 'F:a2', 'G:a3', 'H:a4', 'I:a5 - D', 'J:a6', 'K:a7', 'L:a8', 'M:a9', 'N:a10', 'O:a11', 'P:a12', 'R:a14')),
        ('engine', 'd', 'joint_covariance',
         ('Pb206r_std',),
         ('F:a2', 'G:a3', 'H:a4', 'I:a5 - D', 'J:a6', 'L:a8', 'M:a9', 'N:a10', 'O:a11', 'P:a12', 'R:a14')),
        ('engine', 'e', 'missing_measurement',
         ('FPb', 'FPb_std', 'FU', 'FU_std', 'Pb204b', 'Pb204c', 'Pb204c_std', 'Pb206b', 'Pb206c', 'Pb206r', 'Pb206r_std', 'Pb206s', 'Pb206s_std', 'Pb207b', 'Pb207c', 'Pb207r', 'Pb207r_std', 'Pb207s', 'Pb207s_std', 'Pb208b', 'Pb208c', 'Pb208r', 'Pb208r_std', 'Pb_R45m', 'Pb_R45m_error_pct_1s', 'Pb_R46m', 'Pb_R46m_error_pct_1s', 'Pb_R65m', 'Pb_R65m_error_pct_1s', 'Pb_R75m', 'Pb_R75m_error_pct_1s', 'Pb_R76m', 'Pb_R76m_error_pct_1s', 'Pb_R84m_std', 'Pb_R85m', 'Pb_R85m_error_pct_1s', 'Pb_ppm', 'Pbc_pg', 'Pbr_Pbc', 'Pbr_pg', 'R46s', 'R46s_error_pct_2s', 'R54s', 'R54s_error_pct_2s', 'R64fc', 'R64s', 'R64s_error_pct_2s', 'R68r', 'R68r_Th', 'R68r_Th_error_pct_2s', 'R68r_error_pct_2s', 'R74s', 'R74s_error_pct_2s', 'R75r', 'R75r_Th', 'R75r_Th_error_pct_2s', 'R75r_error_pct_2s', 'R76r', 'R76r_Th', 'R76r_Th_error_pct_2s', 'R76r_error_pct_2s', 'R76s', 'R76s_error_pct_2s', 'R84s', 'R84s_error_pct_2s', 'R86rad', 'R86s', 'R86s_error_pct_2s', 'Th232s', 'Th_U', 'Th_ppm', 'U235s', 'U235s_std', 'U238s', 'U238s_std', 'U_R35m', 'U_R35m_error_pct_1s', 'U_R83m', 'U_R83m_error_pct_1s', 'U_R85m', 'U_R85m_error_pct_1s', 'U_ppm', 'mol_fraction_206r', 'rho_7568_r', 'rho_7646_s', 'rho_8646_s', 'rho_8676_r', 'rho_8676_s', 't68', 't68_Th_corr', 't68_Th_corr_std', 't68_std', 't75', 't75_std', 't76', 't76_Th_corr', 't76_Th_corr_std', 't76_std'),
         ('Q:a13', 'Z:C15 TPB')),
        ('output_table', 'c', 'sheet_U_derivative',
         ('R86s_error_pct_2s', 'rho_8646_s', 'rho_8676_s'),
         ('E:a1', 'K:a7', 'L:a8')),
        ('output_table', 'c', 'sheet_common_mass',
         ('Pbc_export',),
         ('E:a1', 'F:a2', 'G:a3', 'H:a4', 'I:a5 - D', 'J:a6', 'K:a7', 'L:a8', 'M:a9', 'N:a10', 'O:a11', 'P:a12', 'R:a14')),
        ('output_table', 'd', 'date_domain',
         ('Pb206r_scaled', 'Pb_ppm', 'Pbc_export', 'Pbr_Pbc', 'R46s', 'R46s_error_pct_2s', 'R54s', 'R54s_error_pct_2s', 'R64fc', 'R64s', 'R64s_error_pct_2s', 'R68r_Th', 'R68r_Th_error_pct_2s', 'R74s', 'R74s_error_pct_2s', 'R75r', 'R75r_error_pct_2s', 'R76r_Th', 'R76r_Th_error_pct_2s', 'R76s', 'R76s_error_pct_2s', 'R84s', 'R84s_error_pct_2s', 'R86rad', 'R86s', 'R86s_error_pct_2s', 'Th_U', 'U_ppm', 'mol_fraction_206r', 'rho_5474_s', 'rho_7464_s', 'rho_7568_r', 'rho_7646_s', 'rho_8464_s', 'rho_8646_s', 'rho_8676_s', 't68_Th_corr', 't68_Th_corr_std', 't75', 't75_std', 't76_Th_corr', 't76_Th_corr_std'),
         ('X:C13 TPB', 'Y:C14 TPB')),
        ('output_table', 'd', 'joint_covariance',
         ('R68r_Th_error_pct_2s', 'R75r_error_pct_2s', 'R76r_Th_error_pct_2s', 'rho_7568_r', 't68_Th_corr_std', 't75_std', 't76_Th_corr_std'),
         ('E:a1', 'F:a2', 'G:a3', 'H:a4', 'I:a5 - D', 'J:a6', 'K:a7', 'L:a8', 'M:a9', 'N:a10', 'O:a11', 'P:a12', 'R:a14')),
        ('output_table', 'e', 'missing_measurement',
         ('Pb206r_scaled', 'Pb_ppm', 'Pbc_export', 'Pbr_Pbc', 'R46s', 'R46s_error_pct_2s', 'R54s', 'R54s_error_pct_2s', 'R64fc', 'R64s', 'R64s_error_pct_2s', 'R68r_Th', 'R68r_Th_error_pct_2s', 'R74s', 'R74s_error_pct_2s', 'R75r', 'R75r_error_pct_2s', 'R76r_Th', 'R76r_Th_error_pct_2s', 'R76s', 'R76s_error_pct_2s', 'R84s', 'R84s_error_pct_2s', 'R86rad', 'R86s', 'R86s_error_pct_2s', 'Th_U', 'U_ppm', 'mol_fraction_206r', 'rho_5474_s', 'rho_7464_s', 'rho_7568_r', 'rho_7646_s', 'rho_8464_s', 'rho_8646_s', 'rho_8676_s', 't68_Th_corr', 't68_Th_corr_std', 't75', 't75_std', 't76_Th_corr', 't76_Th_corr_std'),
         ('Q:a13', 'Z:C15 TPB')),
    ],
    'MA1_rutile_UPbR24XML.xls': [
        ('csv', 'c', 'sheet_U_derivative',
         ('R86s_error_pct_2s', 'rho_8676_s'),
         ('E:r1',)),
        ('csv', 'c', 'sheet_common_mass',
         ('Pbc_export',),
         ('E:r1', 'F:r2', 'G:r3', 'H:r4', 'I:r5', 'J:r6')),
        ('csv', 'd', 'joint_covariance',
         ('R68r_Th_error_pct_2s', 'R75r_error_pct_2s', 'R76r_Th_error_pct_2s', 'rho_7568_r', 't68_Th_corr_std', 't75_std', 't76_Th_corr_std'),
         ('E:r1', 'F:r2', 'G:r3', 'H:r4', 'I:r5', 'J:r6')),
        ('engine', 'b', 'missing_sample208_covariance',
         ('Pb208sample_std', 'Pb_R84sample_error_pct_2s', 'Pb_R86sample_error_pct_2s', 'rho_Pb8464sample'),
         ('E:r1', 'F:r2', 'G:r3', 'H:r4', 'I:r5', 'J:r6')),
        ('engine', 'c', 'sheet_208_quotient',
         ('Pb_R84m_std',),
         ('E:r1', 'F:r2', 'G:r3', 'H:r4', 'I:r5', 'J:r6')),
        ('engine', 'c', 'sheet_U_derivative',
         ('R86s_error_pct_2s', 'rho_8646_s', 'rho_8676_s'),
         ('E:r1',)),
        ('engine', 'd', 'joint_covariance',
         ('Pb206r_std', 'Pb207r_std', 'Pb208r_std', 'R68r_Th_error_pct_2s', 'R68r_error_pct_2s', 'R75r_Th_error_pct_2s', 'R75r_error_pct_2s', 'R76r_Th_error_pct_2s', 'R76r_error_pct_2s', 'U235s_std', 'U238s_std', 'rho_7568_r', 'rho_8676_r', 't68_Th_corr_std', 't68_std', 't75_std', 't76_Th_corr_std', 't76_std'),
         ('E:r1', 'F:r2', 'G:r3', 'H:r4', 'I:r5', 'J:r6')),
        ('output_table', 'b', 'missing_sample208_covariance',
         ('Pb_R84sample_error_pct_2s', 'rho_Pb8464sample'),
         ('E:r1', 'F:r2', 'G:r3', 'H:r4', 'I:r5', 'J:r6')),
        ('output_table', 'c', 'sheet_U_derivative',
         ('R86s_error_pct_2s', 'rho_8646_s', 'rho_8676_s'),
         ('E:r1',)),
        ('output_table', 'c', 'sheet_common_mass',
         ('Pbc_export',),
         ('E:r1', 'F:r2', 'G:r3', 'H:r4', 'I:r5', 'J:r6')),
        ('output_table', 'd', 'joint_covariance',
         ('R68r_Th_error_pct_2s', 'R75r_error_pct_2s', 'R76r_Th_error_pct_2s', 'rho_7568_r', 't68_Th_corr_std', 't75_std', 't76_Th_corr_std'),
         ('E:r1', 'F:r2', 'G:r3', 'H:r4', 'I:r5', 'J:r6')),
    ],
    'MA12_titanite_UPbR24XML.xls': [
        ('csv', 'c', 'sheet_U_derivative',
         ('R86s_error_pct_2s', 'rho_8676_s'),
         ('I:t5', 'J:t6')),
        ('csv', 'c', 'sheet_common_mass',
         ('Pbc_export',),
         ('E:t1', 'F:t2', 'G:t3', 'H:t4', 'I:t5', 'J:t6', 'L:t8', 'M:t9')),
        ('csv', 'd', 'joint_covariance',
         ('R68r_Th_error_pct_2s', 'R75r_error_pct_2s', 'R76r_Th_error_pct_2s', 'rho_7568_r', 't68_Th_corr_std', 't75_std', 't76_Th_corr_std'),
         ('E:t1', 'F:t2', 'G:t3', 'H:t4', 'I:t5', 'J:t6', 'L:t8', 'M:t9')),
        ('engine', 'b', 'missing_sample208_covariance',
         ('Pb208sample_std', 'Pb_R84sample_error_pct_2s', 'Pb_R86sample_error_pct_2s', 'rho_Pb8464sample'),
         ('E:t1', 'F:t2', 'G:t3', 'H:t4', 'I:t5', 'J:t6', 'L:t8', 'M:t9')),
        ('engine', 'c', 'sheet_208_quotient',
         ('Pb_R84m_std',),
         ('E:t1', 'F:t2', 'G:t3', 'H:t4', 'I:t5', 'J:t6', 'L:t8', 'M:t9')),
        ('engine', 'c', 'sheet_U_derivative',
         ('R86s_error_pct_2s', 'rho_8646_s', 'rho_8676_s'),
         ('I:t5', 'J:t6')),
        ('engine', 'd', 'date_domain',
         ('FPb', 'FPb_std', 'FU', 'FU_std', 'Pb204b', 'Pb204c', 'Pb204c_std', 'Pb206b', 'Pb206c', 'Pb206r', 'Pb206r_std', 'Pb206s', 'Pb206s_std', 'Pb207b', 'Pb207c', 'Pb207r', 'Pb207r_std', 'Pb207s', 'Pb207s_std', 'Pb208b', 'Pb208c', 'Pb208r', 'Pb208r_std', 'Pb208sample', 'Pb208sample_std', 'Pb_R45m', 'Pb_R45m_error_pct_1s', 'Pb_R46m', 'Pb_R46m_error_pct_1s', 'Pb_R65m', 'Pb_R65m_error_pct_1s', 'Pb_R75m', 'Pb_R75m_error_pct_1s', 'Pb_R76m', 'Pb_R76m_error_pct_1s', 'Pb_R84m_std', 'Pb_R84sample', 'Pb_R84sample_error_pct_2s', 'Pb_R85m', 'Pb_R85m_error_pct_1s', 'Pb_R86sample', 'Pb_R86sample_error_pct_2s', 'Pb_ppm', 'Pbc_pg', 'Pbr_Pbc', 'Pbr_pg', 'R46s', 'R46s_error_pct_2s', 'R54s', 'R54s_error_pct_2s', 'R64fc', 'R64s', 'R64s_error_pct_2s', 'R68r', 'R68r_Th', 'R68r_Th_error_pct_2s', 'R68r_error_pct_2s', 'R74s', 'R74s_error_pct_2s', 'R75r', 'R75r_Th', 'R75r_Th_error_pct_2s', 'R75r_error_pct_2s', 'R76r', 'R76r_Th', 'R76r_Th_error_pct_2s', 'R76r_error_pct_2s', 'R76s', 'R76s_error_pct_2s', 'R84s', 'R84s_error_pct_2s', 'R86rad', 'R86s', 'R86s_error_pct_2s', 'Th232s', 'Th_U', 'Th_ppm', 'U235s', 'U235s_std', 'U238s', 'U238s_std', 'U_R35m', 'U_R35m_error_pct_1s', 'U_R83m', 'U_R83m_error_pct_1s', 'U_R85m', 'U_R85m_error_pct_1s', 'U_ppm', 'mol_fraction_206r', 'rho_7568_r', 'rho_7646_s', 'rho_8646_s', 'rho_8676_r', 'rho_8676_s', 'rho_Pb8464sample', 't68', 't68_Th_corr', 't68_Th_corr_std', 't68_std', 't75', 't75_std', 't76', 't76_Th_corr', 't76_Th_corr_std', 't76_std'),
         ('K:t7',)),
        ('engine', 'd', 'joint_covariance',
         ('Pb206r_std', 'Pb207r_std', 'Pb208r_std', 'R68r_Th_error_pct_2s', 'R68r_error_pct_2s', 'R75r_Th_error_pct_2s', 'R75r_error_pct_2s', 'R76r_Th_error_pct_2s', 'R76r_error_pct_2s', 'U235s_std', 'U238s_std', 'rho_7568_r', 'rho_8676_r', 't68_Th_corr_std', 't68_std', 't75_std', 't76_Th_corr_std', 't76_std'),
         ('E:t1', 'F:t2', 'G:t3', 'H:t4', 'I:t5', 'J:t6', 'L:t8', 'M:t9')),
        ('output_table', 'b', 'missing_sample208_covariance',
         ('Pb_R84sample_error_pct_2s', 'rho_Pb8464sample'),
         ('E:t1', 'F:t2', 'G:t3', 'H:t4', 'I:t5', 'J:t6', 'L:t8', 'M:t9')),
        ('output_table', 'c', 'sheet_U_derivative',
         ('R86s_error_pct_2s', 'rho_8646_s', 'rho_8676_s'),
         ('I:t5', 'J:t6')),
        ('output_table', 'c', 'sheet_common_mass',
         ('Pbc_export',),
         ('E:t1', 'F:t2', 'G:t3', 'H:t4', 'I:t5', 'J:t6', 'L:t8', 'M:t9')),
        ('output_table', 'd', 'date_domain',
         ('Pb206r_scaled', 'Pb_R84sample', 'Pb_R84sample_error_pct_2s', 'Pb_ppm', 'Pbc_export', 'Pbr_Pbc', 'R46s', 'R46s_error_pct_2s', 'R54s', 'R54s_error_pct_2s', 'R64fc', 'R64s', 'R64s_error_pct_2s', 'R68r_Th', 'R68r_Th_error_pct_2s', 'R74s', 'R74s_error_pct_2s', 'R75r', 'R75r_error_pct_2s', 'R76r_Th', 'R76r_Th_error_pct_2s', 'R76s', 'R76s_error_pct_2s', 'R84s', 'R84s_error_pct_2s', 'R86rad', 'R86s', 'R86s_error_pct_2s', 'Th_U', 'U_ppm', 'mol_fraction_206r', 'rho_5474_s', 'rho_7464_s', 'rho_7568_r', 'rho_7646_s', 'rho_8464_s', 'rho_8646_s', 'rho_8676_s', 'rho_Pb8464sample', 't68_Th_corr', 't68_Th_corr_std', 't75', 't75_std', 't76_Th_corr', 't76_Th_corr_std'),
         ('K:t7',)),
        ('output_table', 'd', 'joint_covariance',
         ('R68r_Th_error_pct_2s', 'R75r_error_pct_2s', 'R76r_Th_error_pct_2s', 'rho_7568_r', 't68_Th_corr_std', 't75_std', 't76_Th_corr_std'),
         ('E:t1', 'F:t2', 'G:t3', 'H:t4', 'I:t5', 'J:t6', 'L:t8', 'M:t9')),
    ],
    'new-all-Willsboro-gt-cpx_UPbR22XML.xls': [
        ('csv', 'c', 'sheet_U_derivative',
         ('R86s_error_pct_2s', 'rho_8646_s', 'rho_8676_s'),
         ('AA:g4', 'X:g1', 'Y:g2', 'Z:g3')),
        ('csv', 'c', 'sheet_common_mass',
         ('Pbc_export',),
         ('AA:g4', 'AB:g5', 'AC:g6', 'AD:g7', 'AE:g8', 'X:g1', 'Y:g2', 'Z:g3')),
        ('csv', 'd', 'joint_covariance',
         ('R68r_Th_error_pct_2s', 'R75r_error_pct_2s', 'R76r_Th_error_pct_2s', 'rho_7568_r', 't68_Th_corr_std', 't75_std', 't76_Th_corr_std'),
         ('AA:g4', 'AB:g5', 'AC:g6', 'AD:g7', 'AE:g8', 'X:g1', 'Y:g2', 'Z:g3')),
        ('csv', 'e', 'export_settings',
         ('R46s',),
         ('AB:g5',)),
        ('engine', 'b', 'missing_sample208_covariance',
         ('Pb208sample_std', 'Pb_R84sample_error_pct_2s', 'Pb_R86sample_error_pct_2s', 'rho_Pb8464sample'),
         ('AA:g4', 'AB:g5', 'AC:g6', 'AD:g7', 'AE:g8', 'E:g1', 'F:g2', 'G:g3', 'H:g4', 'I:g5a', 'J:g5b', 'K:g6', 'L:g6 FD', 'M:d1', 'N:d2', 'Q:g1', 'R:g2', 'S:g3', 'T:g4', 'U:g5', 'V:g6', 'W:g7', 'X:g1', 'Y:g2', 'Z:g3')),
        ('engine', 'c', 'sheet_208_quotient',
         ('Pb_R84m_std',),
         ('AA:g4', 'AB:g5', 'AC:g6', 'AD:g7', 'AE:g8', 'E:g1', 'F:g2', 'G:g3', 'H:g4', 'I:g5a', 'J:g5b', 'K:g6', 'L:g6 FD', 'M:d1', 'N:d2', 'Q:g1', 'R:g2', 'S:g3', 'T:g4', 'U:g5', 'V:g6', 'W:g7', 'X:g1', 'Y:g2', 'Z:g3')),
        ('engine', 'c', 'sheet_U_derivative',
         ('R86s_error_pct_2s', 'rho_8646_s', 'rho_8676_s'),
         ('AA:g4', 'E:g1', 'F:g2', 'H:g4', 'K:g6', 'L:g6 FD', 'X:g1', 'Y:g2', 'Z:g3')),
        ('engine', 'd', 'date_domain',
         ('FPb', 'FPb_std', 'FU', 'FU_std', 'Pb204b', 'Pb204c', 'Pb204c_std', 'Pb206b', 'Pb206c', 'Pb206r', 'Pb206r_std', 'Pb206s', 'Pb206s_std', 'Pb207b', 'Pb207c', 'Pb207r', 'Pb207r_std', 'Pb207s', 'Pb207s_std', 'Pb208b', 'Pb208c', 'Pb208r', 'Pb208r_std', 'Pb208sample', 'Pb208sample_std', 'Pb_R45m', 'Pb_R45m_error_pct_1s', 'Pb_R46m', 'Pb_R46m_error_pct_1s', 'Pb_R65m', 'Pb_R65m_error_pct_1s', 'Pb_R75m', 'Pb_R75m_error_pct_1s', 'Pb_R76m', 'Pb_R76m_error_pct_1s', 'Pb_R84m_std', 'Pb_R84sample', 'Pb_R84sample_error_pct_2s', 'Pb_R85m', 'Pb_R85m_error_pct_1s', 'Pb_R86sample', 'Pb_R86sample_error_pct_2s', 'Pb_ppm', 'Pbc_pg', 'Pbr_Pbc', 'Pbr_pg', 'R46s', 'R46s_error_pct_2s', 'R54s', 'R54s_error_pct_2s', 'R64fc', 'R64s', 'R64s_error_pct_2s', 'R68r', 'R68r_Th', 'R68r_Th_error_pct_2s', 'R68r_error_pct_2s', 'R74s', 'R74s_error_pct_2s', 'R75r', 'R75r_Th', 'R75r_Th_error_pct_2s', 'R75r_error_pct_2s', 'R76r', 'R76r_Th', 'R76r_Th_error_pct_2s', 'R76r_error_pct_2s', 'R76s', 'R76s_error_pct_2s', 'R84s', 'R84s_error_pct_2s', 'R86rad', 'R86s', 'R86s_error_pct_2s', 'Th232s', 'Th_U', 'Th_ppm', 'U235s', 'U235s_std', 'U238s', 'U238s_std', 'U_R35m', 'U_R35m_error_pct_1s', 'U_R83m', 'U_R83m_error_pct_1s', 'U_R85m', 'U_R85m_error_pct_1s', 'U_ppm', 'mol_fraction_206r', 'rho_7568_r', 'rho_7646_s', 'rho_8646_s', 'rho_8676_r', 'rho_8676_s', 'rho_Pb8464sample', 't68', 't68_Th_corr', 't68_Th_corr_std', 't68_std', 't75', 't75_std', 't76', 't76_Th_corr', 't76_Th_corr_std', 't76_std'),
         ('AF:TPB-g1', 'AG:TPB-g2', 'AH:TPB-g3', 'O:d3', 'P:d4')),
        ('engine', 'd', 'joint_covariance',
         ('Pb206r_std', 'Pb207r_std', 'Pb208r_std', 'R68r_Th_error_pct_2s', 'R68r_error_pct_2s', 'R75r_Th_error_pct_2s', 'R75r_error_pct_2s', 'R76r_Th_error_pct_2s', 'R76r_error_pct_2s', 'U235s_std', 'U238s_std', 'rho_7568_r', 'rho_8676_r', 't68_Th_corr_std', 't68_std', 't75_std', 't76_Th_corr_std', 't76_std'),
         ('AA:g4', 'AB:g5', 'AC:g6', 'AD:g7', 'AE:g8', 'E:g1', 'F:g2', 'G:g3', 'H:g4', 'I:g5a', 'J:g5b', 'K:g6', 'L:g6 FD', 'M:d1', 'N:d2', 'Q:g1', 'R:g2', 'S:g3', 'T:g4', 'U:g5', 'V:g6', 'W:g7', 'X:g1', 'Y:g2', 'Z:g3')),
        ('output_table', 'b', 'missing_sample208_covariance',
         ('Pb_R84sample_error_pct_2s', 'rho_Pb8464sample'),
         ('AA:g4', 'AB:g5', 'AC:g6', 'AD:g7', 'AE:g8', 'E:g1', 'F:g2', 'G:g3', 'H:g4', 'I:g5a', 'J:g5b', 'K:g6', 'L:g6 FD', 'M:d1', 'N:d2', 'Q:g1', 'R:g2', 'S:g3', 'T:g4', 'U:g5', 'V:g6', 'W:g7', 'X:g1', 'Y:g2', 'Z:g3')),
        ('output_table', 'c', 'sheet_U_derivative',
         ('R86s_error_pct_2s', 'rho_8646_s', 'rho_8676_s'),
         ('AA:g4', 'E:g1', 'F:g2', 'H:g4', 'K:g6', 'L:g6 FD', 'X:g1', 'Y:g2', 'Z:g3')),
        ('output_table', 'c', 'sheet_common_mass',
         ('Pbc_export',),
         ('AA:g4', 'AB:g5', 'AC:g6', 'AD:g7', 'AE:g8', 'E:g1', 'F:g2', 'G:g3', 'H:g4', 'I:g5a', 'J:g5b', 'K:g6', 'L:g6 FD', 'M:d1', 'N:d2', 'Q:g1', 'R:g2', 'S:g3', 'T:g4', 'U:g5', 'V:g6', 'W:g7', 'X:g1', 'Y:g2', 'Z:g3')),
        ('output_table', 'd', 'date_domain',
         ('Pb206r_scaled', 'Pb_R84sample', 'Pb_R84sample_error_pct_2s', 'Pb_ppm', 'Pbc_export', 'Pbr_Pbc', 'R46s', 'R46s_error_pct_2s', 'R54s', 'R54s_error_pct_2s', 'R64fc', 'R64s', 'R64s_error_pct_2s', 'R68r_Th', 'R68r_Th_error_pct_2s', 'R74s', 'R74s_error_pct_2s', 'R75r', 'R75r_error_pct_2s', 'R76r_Th', 'R76r_Th_error_pct_2s', 'R76s', 'R76s_error_pct_2s', 'R84s', 'R84s_error_pct_2s', 'R86rad', 'R86s', 'R86s_error_pct_2s', 'Th_U', 'U_ppm', 'mol_fraction_206r', 'rho_5474_s', 'rho_7464_s', 'rho_7568_r', 'rho_7646_s', 'rho_8464_s', 'rho_8646_s', 'rho_8676_s', 'rho_Pb8464sample', 't68_Th_corr', 't68_Th_corr_std', 't75', 't75_std', 't76_Th_corr', 't76_Th_corr_std'),
         ('AF:TPB-g1', 'AG:TPB-g2', 'AH:TPB-g3', 'O:d3', 'P:d4')),
        ('output_table', 'd', 'joint_covariance',
         ('R68r_Th_error_pct_2s', 'R75r_error_pct_2s', 'R76r_Th_error_pct_2s', 'rho_7568_r', 't68_Th_corr_std', 't75_std', 't76_Th_corr_std'),
         ('AA:g4', 'AB:g5', 'AC:g6', 'AD:g7', 'AE:g8', 'E:g1', 'F:g2', 'G:g3', 'H:g4', 'I:g5a', 'J:g5b', 'K:g6', 'L:g6 FD', 'M:d1', 'N:d2', 'Q:g1', 'R:g2', 'S:g3', 'T:g4', 'U:g5', 'V:g6', 'W:g7', 'X:g1', 'Y:g2', 'Z:g3')),
    ],
}

EXPECTED_FRACTIONS = {
    'MA1_zircon_UPbR21XML.xls': ('E:z1', 'F:z2', 'G:z3', 'H:z4', 'I:z5', 'J:z6', 'K:z7', 'L:z8', 'M:z9a', 'N:z9b', 'O:z10a', 'P:z10b'),
    'MA1_apatite_UPbR21XML.xls': ('E:a1', 'F:a2', 'G:a3', 'H:a4', 'I:a5', 'J:a6', 'K:a7', 'L:a8', 'M:a9', 'N:a10', 'O:a11', 'P:a12', 'Q:a13', 'Y:C13 TPB', 'Z:C14 TPB', 'AA:C15 TPB'),
    'MA5_zircon_UPbR21XML.xls': ('E:z1', 'F:z2', 'G:z3', 'H:z4', 'I:z5', 'J:z6', 'K:z7', 'L:z8', 'M:z9a', 'N:z9b'),
    'MA5_apatite_UPbR21XML.xls': ('E:a1', 'F:a2', 'G:a3', 'H:a4', 'I:a5 - D', 'J:a6', 'K:a7', 'L:a8', 'M:a9', 'N:a10', 'O:a11', 'P:a12', 'Q:a13', 'R:a14', 'X:C13 TPB', 'Y:C14 TPB', 'Z:C15 TPB'),
    'MA1_rutile_UPbR24XML.xls': ('E:r1', 'F:r2', 'G:r3', 'H:r4', 'I:r5', 'J:r6'),
    'MA12_titanite_UPbR24XML.xls': ('E:t1', 'F:t2', 'G:t3', 'H:t4', 'I:t5', 'J:t6', 'K:t7', 'L:t8', 'M:t9'),
    'new-all-Willsboro-gt-cpx_UPbR22XML.xls': ('E:g1', 'F:g2', 'G:g3', 'H:g4', 'I:g5a', 'J:g5b', 'K:g6', 'L:g6 FD', 'M:d1', 'N:d2', 'O:d3', 'P:d4', 'Q:g1', 'R:g2', 'S:g3', 'T:g4', 'U:g5', 'V:g6', 'W:g7', 'X:g1', 'Y:g2', 'Z:g3', 'AA:g4', 'AB:g5', 'AC:g6', 'AD:g7', 'AE:g8', 'AF:TPB-g1', 'AG:TPB-g2', 'AH:TPB-g3'),
}

# Exact comparison coverage, including repeated output cells.
# source, multiplicity, quantities, fractions (no cached measurements).
EXPECTED_CHECK_COUNTS = {
    'MA1_zircon_UPbR21XML.xls': [
        ('csv', 1,
         ('Pb206r_scaled', 'Pb_ppm', 'Pbc_export', 'Pbr_Pbc', 'R64fc', 'R68r_Th', 'R68r_Th_error_pct_2s', 'R75r', 'R75r_error_pct_2s', 'R76r_Th', 'R76r_Th_error_pct_2s', 'R86rad', 'Th_U', 'U_ppm', 'mol_fraction_206r', 'rho_7568_r', 't68_Th_corr', 't68_Th_corr_std', 't75', 't75_std', 't76_Th_corr', 't76_Th_corr_std'),
         ('E:z1', 'F:z2', 'G:z3', 'H:z4', 'I:z5', 'J:z6', 'K:z7', 'L:z8', 'N:z9b', 'O:z10a', 'P:z10b')),
        ('engine', 1,
         ('FPb', 'FPb_std', 'FU', 'FU_std', 'Pb204b', 'Pb204c', 'Pb204c_std', 'Pb206b', 'Pb206c', 'Pb206r', 'Pb206r_std', 'Pb206s', 'Pb206s_std', 'Pb207b', 'Pb207c', 'Pb207r', 'Pb207r_std', 'Pb207s', 'Pb207s_std', 'Pb208b', 'Pb208c', 'Pb208r', 'Pb208r_std', 'Pb_R45m', 'Pb_R45m_error_pct_1s', 'Pb_R46m', 'Pb_R46m_error_pct_1s', 'Pb_R65m', 'Pb_R65m_error_pct_1s', 'Pb_R75m', 'Pb_R75m_error_pct_1s', 'Pb_R76m', 'Pb_R76m_error_pct_1s', 'Pb_R84m_std', 'Pb_R85m', 'Pb_R85m_error_pct_1s', 'Pb_ppm', 'Pbc_pg', 'Pbr_Pbc', 'Pbr_pg', 'R46s', 'R46s_error_pct_2s', 'R54s', 'R54s_error_pct_2s', 'R64fc', 'R64s', 'R64s_error_pct_2s', 'R68r', 'R68r_Th', 'R68r_Th_error_pct_2s', 'R68r_error_pct_2s', 'R74s', 'R74s_error_pct_2s', 'R75r', 'R75r_Th', 'R75r_Th_error_pct_2s', 'R75r_error_pct_2s', 'R76r', 'R76r_Th', 'R76r_Th_error_pct_2s', 'R76r_error_pct_2s', 'R76s', 'R76s_error_pct_2s', 'R84s', 'R84s_error_pct_2s', 'R86rad', 'R86s', 'R86s_error_pct_2s', 'Th232s', 'Th_U', 'Th_ppm', 'U235s', 'U235s_std', 'U238s', 'U238s_std', 'U_R35m', 'U_R35m_error_pct_1s', 'U_R83m', 'U_R83m_error_pct_1s', 'U_R85m', 'U_R85m_error_pct_1s', 'U_ppm', 'mol_fraction_206r', 'rho_7568_r', 'rho_7646_s', 'rho_8646_s', 'rho_8676_r', 'rho_8676_s', 't68', 't68_Th_corr', 't68_Th_corr_std', 't68_std', 't75', 't75_std', 't76', 't76_Th_corr', 't76_Th_corr_std', 't76_std'),
         ('E:z1', 'F:z2', 'G:z3', 'H:z4', 'I:z5', 'J:z6', 'K:z7', 'L:z8', 'M:z9a', 'N:z9b', 'O:z10a', 'P:z10b')),
        ('output_table', 1,
         ('Pb206r_scaled', 'Pb_ppm', 'Pbc_export', 'Pbr_Pbc', 'R46s', 'R46s_error_pct_2s', 'R54s', 'R54s_error_pct_2s', 'R64fc', 'R68r_Th', 'R68r_Th_error_pct_2s', 'R75r', 'R75r_error_pct_2s', 'R76r_Th', 'R76r_Th_error_pct_2s', 'R76s', 'R76s_error_pct_2s', 'R84s', 'R84s_error_pct_2s', 'R86rad', 'R86s', 'R86s_error_pct_2s', 'Th_U', 'U_ppm', 'mol_fraction_206r', 'rho_5474_s', 'rho_7464_s', 'rho_7568_r', 'rho_7646_s', 'rho_8464_s', 'rho_8646_s', 'rho_8676_s', 't68_Th_corr', 't68_Th_corr_std', 't75', 't75_std', 't76_Th_corr', 't76_Th_corr_std'),
         ('E:z1', 'F:z2', 'G:z3', 'H:z4', 'I:z5', 'J:z6', 'K:z7', 'L:z8', 'M:z9a', 'N:z9b', 'O:z10a', 'P:z10b')),
        ('output_table', 2,
         ('R64s', 'R64s_error_pct_2s', 'R74s', 'R74s_error_pct_2s'),
         ('E:z1', 'F:z2', 'G:z3', 'H:z4', 'I:z5', 'J:z6', 'K:z7', 'L:z8', 'M:z9a', 'N:z9b', 'O:z10a', 'P:z10b')),
        ('publication', 1,
         ('Pb206r_scaled', 'Pbc_export', 'Pbr_Pbc', 'Pbr_pg', 'R64fc', 'R68r_Th', 'R68r_Th_error_pct_2s', 'R75r', 'R75r_error_pct_2s', 'R76r_Th', 'R76r_Th_error_pct_2s', 'R86rad', 'Th_U', 'mol_fraction_206r', 'rho_7568_r', 't68_Th_corr', 't68_Th_corr_std', 't75', 't75_std', 't76_Th_corr', 't76_Th_corr_std'),
         ('E:z1', 'F:z2', 'G:z3', 'H:z4', 'I:z5', 'J:z6', 'K:z7', 'L:z8', 'N:z9b', 'O:z10a', 'P:z10b')),
    ],
    'MA1_apatite_UPbR21XML.xls': [
        ('csv', 1,
         ('Pb206r_scaled', 'Pb_ppm', 'Pbc_export', 'Pbr_Pbc', 'R64fc', 'R68r_Th', 'R68r_Th_error_pct_2s', 'R75r', 'R75r_error_pct_2s', 'R76r_Th', 'R76r_Th_error_pct_2s', 'R76s', 'R76s_error_pct_2s', 'R86rad', 'R86s', 'R86s_error_pct_2s', 'Th_U', 'U_ppm', 'mol_fraction_206r', 'rho_7568_r', 'rho_8676_s', 't68_Th_corr', 't68_Th_corr_std', 't75', 't75_std', 't76_Th_corr', 't76_Th_corr_std'),
         ('E:a1', 'F:a2', 'G:a3', 'H:a4', 'I:a5', 'J:a6', 'K:a7', 'L:a8', 'M:a9', 'N:a10', 'O:a11', 'P:a12', 'Q:a13')),
        ('engine', 1,
         ('FPb', 'FPb_std', 'FU', 'FU_std', 'Pb204b', 'Pb204c', 'Pb204c_std', 'Pb206b', 'Pb206c', 'Pb206r', 'Pb206r_std', 'Pb206s', 'Pb206s_std', 'Pb207b', 'Pb207c', 'Pb207r', 'Pb207r_std', 'Pb207s', 'Pb207s_std', 'Pb208b', 'Pb208c', 'Pb208r', 'Pb208r_std', 'Pb_R45m', 'Pb_R45m_error_pct_1s', 'Pb_R46m', 'Pb_R46m_error_pct_1s', 'Pb_R65m', 'Pb_R65m_error_pct_1s', 'Pb_R75m', 'Pb_R75m_error_pct_1s', 'Pb_R76m', 'Pb_R76m_error_pct_1s', 'Pb_R84m_std', 'Pb_R85m', 'Pb_R85m_error_pct_1s', 'Pb_ppm', 'Pbc_pg', 'Pbr_Pbc', 'Pbr_pg', 'R46s', 'R46s_error_pct_2s', 'R54s', 'R54s_error_pct_2s', 'R64fc', 'R64s', 'R64s_error_pct_2s', 'R68r', 'R68r_Th', 'R68r_Th_error_pct_2s', 'R68r_error_pct_2s', 'R74s', 'R74s_error_pct_2s', 'R75r', 'R75r_Th', 'R75r_Th_error_pct_2s', 'R75r_error_pct_2s', 'R76r', 'R76r_Th', 'R76r_Th_error_pct_2s', 'R76r_error_pct_2s', 'R76s', 'R76s_error_pct_2s', 'R84s', 'R84s_error_pct_2s', 'R86rad', 'R86s', 'R86s_error_pct_2s', 'Th232s', 'Th_U', 'Th_ppm', 'U235s', 'U235s_std', 'U238s', 'U238s_std', 'U_R35m', 'U_R35m_error_pct_1s', 'U_R83m', 'U_R83m_error_pct_1s', 'U_R85m', 'U_R85m_error_pct_1s', 'U_ppm', 'mol_fraction_206r', 'rho_7568_r', 'rho_7646_s', 'rho_8646_s', 'rho_8676_r', 'rho_8676_s', 't68', 't68_Th_corr', 't68_Th_corr_std', 't68_std', 't75', 't75_std', 't76', 't76_Th_corr', 't76_Th_corr_std', 't76_std'),
         ('E:a1', 'F:a2', 'G:a3', 'H:a4', 'I:a5', 'J:a6', 'K:a7', 'L:a8', 'M:a9', 'N:a10', 'O:a11', 'P:a12', 'Q:a13', 'Y:C13 TPB', 'Z:C14 TPB', 'AA:C15 TPB')),
        ('output_table', 1,
         ('Pb206r_scaled', 'Pb_ppm', 'Pbc_export', 'Pbr_Pbc', 'R46s', 'R46s_error_pct_2s', 'R54s', 'R54s_error_pct_2s', 'R64fc', 'R68r_Th', 'R68r_Th_error_pct_2s', 'R75r', 'R75r_error_pct_2s', 'R76r_Th', 'R76r_Th_error_pct_2s', 'R76s', 'R76s_error_pct_2s', 'R84s', 'R84s_error_pct_2s', 'R86rad', 'R86s', 'R86s_error_pct_2s', 'Th_U', 'U_ppm', 'mol_fraction_206r', 'rho_5474_s', 'rho_7464_s', 'rho_7568_r', 'rho_7646_s', 'rho_8464_s', 'rho_8646_s', 'rho_8676_s', 't68_Th_corr', 't68_Th_corr_std', 't75', 't75_std', 't76_Th_corr', 't76_Th_corr_std'),
         ('E:a1', 'F:a2', 'G:a3', 'H:a4', 'I:a5', 'J:a6', 'K:a7', 'L:a8', 'M:a9', 'N:a10', 'O:a11', 'P:a12', 'Q:a13', 'Y:C13 TPB', 'Z:C14 TPB', 'AA:C15 TPB')),
        ('output_table', 2,
         ('R64s', 'R64s_error_pct_2s', 'R74s', 'R74s_error_pct_2s'),
         ('E:a1', 'F:a2', 'G:a3', 'H:a4', 'I:a5', 'J:a6', 'K:a7', 'L:a8', 'M:a9', 'N:a10', 'O:a11', 'P:a12', 'Q:a13', 'Y:C13 TPB', 'Z:C14 TPB', 'AA:C15 TPB')),
    ],
    'MA5_zircon_UPbR21XML.xls': [
        ('csv', 1,
         ('Pb206r_scaled', 'Pb_ppm', 'Pbc_export', 'Pbr_Pbc', 'R64fc', 'R68r_Th', 'R68r_Th_error_pct_2s', 'R75r', 'R75r_error_pct_2s', 'R76r_Th', 'R76r_Th_error_pct_2s', 'R86rad', 'Th_U', 'U_ppm', 'mol_fraction_206r', 'rho_7568_r', 't68_Th_corr', 't68_Th_corr_std', 't75', 't75_std', 't76_Th_corr', 't76_Th_corr_std'),
         ('E:z1', 'F:z2', 'G:z3', 'I:z5', 'J:z6', 'K:z7', 'L:z8', 'M:z9a')),
        ('engine', 1,
         ('FPb', 'FPb_std', 'FU', 'FU_std', 'Pb204b', 'Pb204c', 'Pb204c_std', 'Pb206b', 'Pb206c', 'Pb206r', 'Pb206r_std', 'Pb206s', 'Pb206s_std', 'Pb207b', 'Pb207c', 'Pb207r', 'Pb207r_std', 'Pb207s', 'Pb207s_std', 'Pb208b', 'Pb208c', 'Pb208r', 'Pb208r_std', 'Pb_R45m', 'Pb_R45m_error_pct_1s', 'Pb_R46m', 'Pb_R46m_error_pct_1s', 'Pb_R65m', 'Pb_R65m_error_pct_1s', 'Pb_R75m', 'Pb_R75m_error_pct_1s', 'Pb_R76m', 'Pb_R76m_error_pct_1s', 'Pb_R84m_std', 'Pb_R85m', 'Pb_R85m_error_pct_1s', 'Pb_ppm', 'Pbc_pg', 'Pbr_Pbc', 'Pbr_pg', 'R46s', 'R46s_error_pct_2s', 'R54s', 'R54s_error_pct_2s', 'R64fc', 'R64s', 'R64s_error_pct_2s', 'R68r', 'R68r_Th', 'R68r_Th_error_pct_2s', 'R68r_error_pct_2s', 'R74s', 'R74s_error_pct_2s', 'R75r', 'R75r_Th', 'R75r_Th_error_pct_2s', 'R75r_error_pct_2s', 'R76r', 'R76r_Th', 'R76r_Th_error_pct_2s', 'R76r_error_pct_2s', 'R76s', 'R76s_error_pct_2s', 'R84s', 'R84s_error_pct_2s', 'R86rad', 'R86s', 'R86s_error_pct_2s', 'Th232s', 'Th_U', 'Th_ppm', 'U235s', 'U235s_std', 'U238s', 'U238s_std', 'U_R35m', 'U_R35m_error_pct_1s', 'U_R83m', 'U_R83m_error_pct_1s', 'U_R85m', 'U_R85m_error_pct_1s', 'U_ppm', 'mol_fraction_206r', 'rho_7568_r', 'rho_7646_s', 'rho_8646_s', 'rho_8676_r', 'rho_8676_s', 't68', 't68_Th_corr', 't68_Th_corr_std', 't68_std', 't75', 't75_std', 't76', 't76_Th_corr', 't76_Th_corr_std', 't76_std'),
         ('E:z1', 'F:z2', 'G:z3', 'H:z4', 'I:z5', 'J:z6', 'K:z7', 'L:z8', 'M:z9a', 'N:z9b')),
        ('output_table', 1,
         ('Pb206r_scaled', 'Pb_ppm', 'Pbc_export', 'Pbr_Pbc', 'R46s', 'R46s_error_pct_2s', 'R54s', 'R54s_error_pct_2s', 'R64fc', 'R68r_Th', 'R68r_Th_error_pct_2s', 'R75r', 'R75r_error_pct_2s', 'R76r_Th', 'R76r_Th_error_pct_2s', 'R76s', 'R76s_error_pct_2s', 'R84s', 'R84s_error_pct_2s', 'R86rad', 'R86s', 'R86s_error_pct_2s', 'Th_U', 'U_ppm', 'mol_fraction_206r', 'rho_5474_s', 'rho_7464_s', 'rho_7568_r', 'rho_7646_s', 'rho_8464_s', 'rho_8646_s', 'rho_8676_s', 't68_Th_corr', 't68_Th_corr_std', 't75', 't75_std', 't76_Th_corr', 't76_Th_corr_std'),
         ('E:z1', 'F:z2', 'G:z3', 'H:z4', 'I:z5', 'J:z6', 'K:z7', 'L:z8', 'M:z9a')),
        ('output_table', 2,
         ('R64s', 'R64s_error_pct_2s', 'R74s', 'R74s_error_pct_2s'),
         ('E:z1', 'F:z2', 'G:z3', 'H:z4', 'I:z5', 'J:z6', 'K:z7', 'L:z8', 'M:z9a')),
        ('publication', 1,
         ('Pb206r_scaled', 'Pbc_export', 'Pbr_Pbc', 'Pbr_pg', 'R64fc', 'R68r_Th', 'R68r_Th_error_pct_2s', 'R75r', 'R75r_error_pct_2s', 'R76r_Th', 'R76r_Th_error_pct_2s', 'R86rad', 'Th_U', 'mol_fraction_206r', 'rho_7568_r', 't68_Th_corr', 't68_Th_corr_std', 't75', 't75_std', 't76_Th_corr', 't76_Th_corr_std'),
         ('E:z1', 'F:z2', 'G:z3', 'I:z5', 'J:z6', 'K:z7', 'L:z8', 'M:z9a')),
    ],
    'MA5_apatite_UPbR21XML.xls': [
        ('csv', 1,
         ('Pb206r_scaled', 'Pb_ppm', 'Pbc_export', 'Pbr_Pbc', 'R64fc', 'R68r_Th', 'R68r_Th_error_pct_2s', 'R75r', 'R75r_error_pct_2s', 'R76r_Th', 'R76r_Th_error_pct_2s', 'R76s', 'R76s_error_pct_2s', 'R86rad', 'R86s', 'R86s_error_pct_2s', 'Th_U', 'U_ppm', 'mol_fraction_206r', 'rho_7568_r', 'rho_8676_s', 't68_Th_corr', 't68_Th_corr_std', 't75', 't75_std', 't76_Th_corr', 't76_Th_corr_std'),
         ('E:a1', 'F:a2', 'G:a3', 'H:a4', 'I:a5 - D', 'J:a6', 'K:a7', 'L:a8', 'M:a9', 'N:a10', 'O:a11', 'P:a12', 'R:a14')),
        ('engine', 1,
         ('FPb', 'FPb_std', 'FU', 'FU_std', 'Pb204b', 'Pb204c', 'Pb204c_std', 'Pb206b', 'Pb206c', 'Pb206r', 'Pb206r_std', 'Pb206s', 'Pb206s_std', 'Pb207b', 'Pb207c', 'Pb207r', 'Pb207r_std', 'Pb207s', 'Pb207s_std', 'Pb208b', 'Pb208c', 'Pb208r', 'Pb208r_std', 'Pb_R45m', 'Pb_R45m_error_pct_1s', 'Pb_R46m', 'Pb_R46m_error_pct_1s', 'Pb_R65m', 'Pb_R65m_error_pct_1s', 'Pb_R75m', 'Pb_R75m_error_pct_1s', 'Pb_R76m', 'Pb_R76m_error_pct_1s', 'Pb_R84m_std', 'Pb_R85m', 'Pb_R85m_error_pct_1s', 'Pb_ppm', 'Pbc_pg', 'Pbr_Pbc', 'Pbr_pg', 'R46s', 'R46s_error_pct_2s', 'R54s', 'R54s_error_pct_2s', 'R64fc', 'R64s', 'R64s_error_pct_2s', 'R68r', 'R68r_Th', 'R68r_Th_error_pct_2s', 'R68r_error_pct_2s', 'R74s', 'R74s_error_pct_2s', 'R75r', 'R75r_Th', 'R75r_Th_error_pct_2s', 'R75r_error_pct_2s', 'R76r', 'R76r_Th', 'R76r_Th_error_pct_2s', 'R76r_error_pct_2s', 'R76s', 'R76s_error_pct_2s', 'R84s', 'R84s_error_pct_2s', 'R86rad', 'R86s', 'R86s_error_pct_2s', 'Th232s', 'Th_U', 'Th_ppm', 'U235s', 'U235s_std', 'U238s', 'U238s_std', 'U_R35m', 'U_R35m_error_pct_1s', 'U_R83m', 'U_R83m_error_pct_1s', 'U_R85m', 'U_R85m_error_pct_1s', 'U_ppm', 'mol_fraction_206r', 'rho_7568_r', 'rho_7646_s', 'rho_8646_s', 'rho_8676_r', 'rho_8676_s', 't68', 't68_Th_corr', 't68_Th_corr_std', 't68_std', 't75', 't75_std', 't76', 't76_Th_corr', 't76_Th_corr_std', 't76_std'),
         ('E:a1', 'F:a2', 'G:a3', 'H:a4', 'I:a5 - D', 'J:a6', 'K:a7', 'L:a8', 'M:a9', 'N:a10', 'O:a11', 'P:a12', 'Q:a13', 'R:a14', 'X:C13 TPB', 'Y:C14 TPB', 'Z:C15 TPB')),
        ('output_table', 1,
         ('Pb206r_scaled', 'Pb_ppm', 'Pbc_export', 'Pbr_Pbc', 'R46s', 'R46s_error_pct_2s', 'R54s', 'R54s_error_pct_2s', 'R64fc', 'R68r_Th', 'R68r_Th_error_pct_2s', 'R75r', 'R75r_error_pct_2s', 'R76r_Th', 'R76r_Th_error_pct_2s', 'R76s', 'R76s_error_pct_2s', 'R84s', 'R84s_error_pct_2s', 'R86rad', 'R86s', 'R86s_error_pct_2s', 'Th_U', 'U_ppm', 'mol_fraction_206r', 'rho_5474_s', 'rho_7464_s', 'rho_7568_r', 'rho_7646_s', 'rho_8464_s', 'rho_8646_s', 'rho_8676_s', 't68_Th_corr', 't68_Th_corr_std', 't75', 't75_std', 't76_Th_corr', 't76_Th_corr_std'),
         ('E:a1', 'F:a2', 'G:a3', 'H:a4', 'I:a5 - D', 'J:a6', 'K:a7', 'L:a8', 'M:a9', 'N:a10', 'O:a11', 'P:a12', 'Q:a13', 'R:a14', 'X:C13 TPB', 'Y:C14 TPB', 'Z:C15 TPB')),
        ('output_table', 2,
         ('R64s', 'R64s_error_pct_2s', 'R74s', 'R74s_error_pct_2s'),
         ('E:a1', 'F:a2', 'G:a3', 'H:a4', 'I:a5 - D', 'J:a6', 'K:a7', 'L:a8', 'M:a9', 'N:a10', 'O:a11', 'P:a12', 'Q:a13', 'R:a14', 'X:C13 TPB', 'Y:C14 TPB', 'Z:C15 TPB')),
    ],
    'MA1_rutile_UPbR24XML.xls': [
        ('csv', 1,
         ('Pb206r_scaled', 'Pb_ppm', 'Pbc_export', 'Pbr_Pbc', 'R64fc', 'R68r_Th', 'R68r_Th_error_pct_2s', 'R75r', 'R75r_error_pct_2s', 'R76r_Th', 'R76r_Th_error_pct_2s', 'R76s', 'R76s_error_pct_2s', 'R86rad', 'R86s', 'R86s_error_pct_2s', 'Th_U', 'U_ppm', 'mol_fraction_206r', 'rho_7568_r', 'rho_8676_s', 't68_Th_corr', 't68_Th_corr_std', 't75', 't75_std', 't76_Th_corr', 't76_Th_corr_std'),
         ('E:r1', 'F:r2', 'G:r3', 'H:r4', 'I:r5', 'J:r6')),
        ('engine', 1,
         ('FPb', 'FPb_std', 'FU', 'FU_std', 'Pb204b', 'Pb204c', 'Pb204c_std', 'Pb206b', 'Pb206c', 'Pb206r', 'Pb206r_std', 'Pb206s', 'Pb206s_std', 'Pb207b', 'Pb207c', 'Pb207r', 'Pb207r_std', 'Pb207s', 'Pb207s_std', 'Pb208b', 'Pb208c', 'Pb208r', 'Pb208r_std', 'Pb208sample', 'Pb208sample_std', 'Pb_R45m', 'Pb_R45m_error_pct_1s', 'Pb_R46m', 'Pb_R46m_error_pct_1s', 'Pb_R65m', 'Pb_R65m_error_pct_1s', 'Pb_R75m', 'Pb_R75m_error_pct_1s', 'Pb_R76m', 'Pb_R76m_error_pct_1s', 'Pb_R84m_std', 'Pb_R84sample', 'Pb_R84sample_error_pct_2s', 'Pb_R85m', 'Pb_R85m_error_pct_1s', 'Pb_R86sample', 'Pb_R86sample_error_pct_2s', 'Pb_ppm', 'Pbc_pg', 'Pbr_Pbc', 'Pbr_pg', 'R46s', 'R46s_error_pct_2s', 'R54s', 'R54s_error_pct_2s', 'R64fc', 'R64s', 'R64s_error_pct_2s', 'R68r', 'R68r_Th', 'R68r_Th_error_pct_2s', 'R68r_error_pct_2s', 'R74s', 'R74s_error_pct_2s', 'R75r', 'R75r_Th', 'R75r_Th_error_pct_2s', 'R75r_error_pct_2s', 'R76r', 'R76r_Th', 'R76r_Th_error_pct_2s', 'R76r_error_pct_2s', 'R76s', 'R76s_error_pct_2s', 'R84s', 'R84s_error_pct_2s', 'R86rad', 'R86s', 'R86s_error_pct_2s', 'Th232s', 'Th_U', 'Th_ppm', 'U235s', 'U235s_std', 'U238s', 'U238s_std', 'U_R35m', 'U_R35m_error_pct_1s', 'U_R83m', 'U_R83m_error_pct_1s', 'U_R85m', 'U_R85m_error_pct_1s', 'U_ppm', 'mol_fraction_206r', 'rho_7568_r', 'rho_7646_s', 'rho_8646_s', 'rho_8676_r', 'rho_8676_s', 'rho_Pb8464sample', 't68', 't68_Th_corr', 't68_Th_corr_std', 't68_std', 't75', 't75_std', 't76', 't76_Th_corr', 't76_Th_corr_std', 't76_std'),
         ('E:r1', 'F:r2', 'G:r3', 'H:r4', 'I:r5', 'J:r6')),
        ('output_table', 1,
         ('Pb206r_scaled', 'Pb_R84sample', 'Pb_R84sample_error_pct_2s', 'Pb_ppm', 'Pbc_export', 'Pbr_Pbc', 'R46s', 'R46s_error_pct_2s', 'R54s', 'R54s_error_pct_2s', 'R64fc', 'R68r_Th', 'R68r_Th_error_pct_2s', 'R75r', 'R75r_error_pct_2s', 'R76r_Th', 'R76r_Th_error_pct_2s', 'R76s', 'R76s_error_pct_2s', 'R84s', 'R84s_error_pct_2s', 'R86rad', 'R86s', 'R86s_error_pct_2s', 'Th_U', 'U_ppm', 'mol_fraction_206r', 'rho_5474_s', 'rho_7464_s', 'rho_7568_r', 'rho_7646_s', 'rho_8464_s', 'rho_8646_s', 'rho_8676_s', 'rho_Pb8464sample', 't68_Th_corr', 't68_Th_corr_std', 't75', 't75_std', 't76_Th_corr', 't76_Th_corr_std'),
         ('E:r1', 'F:r2', 'G:r3', 'H:r4', 'I:r5', 'J:r6')),
        ('output_table', 2,
         ('R74s', 'R74s_error_pct_2s'),
         ('E:r1', 'F:r2', 'G:r3', 'H:r4', 'I:r5', 'J:r6')),
        ('output_table', 3,
         ('R64s', 'R64s_error_pct_2s'),
         ('E:r1', 'F:r2', 'G:r3', 'H:r4', 'I:r5', 'J:r6')),
    ],
    'MA12_titanite_UPbR24XML.xls': [
        ('csv', 1,
         ('Pb206r_scaled', 'Pb_ppm', 'Pbc_export', 'Pbr_Pbc', 'R64fc', 'R68r_Th', 'R68r_Th_error_pct_2s', 'R75r', 'R75r_error_pct_2s', 'R76r_Th', 'R76r_Th_error_pct_2s', 'R76s', 'R76s_error_pct_2s', 'R86rad', 'R86s', 'R86s_error_pct_2s', 'Th_U', 'U_ppm', 'mol_fraction_206r', 'rho_7568_r', 'rho_8676_s', 't68_Th_corr', 't68_Th_corr_std', 't75', 't75_std', 't76_Th_corr', 't76_Th_corr_std'),
         ('E:t1', 'F:t2', 'G:t3', 'H:t4', 'I:t5', 'J:t6', 'L:t8', 'M:t9')),
        ('engine', 1,
         ('FPb', 'FPb_std', 'FU', 'FU_std', 'Pb204b', 'Pb204c', 'Pb204c_std', 'Pb206b', 'Pb206c', 'Pb206r', 'Pb206r_std', 'Pb206s', 'Pb206s_std', 'Pb207b', 'Pb207c', 'Pb207r', 'Pb207r_std', 'Pb207s', 'Pb207s_std', 'Pb208b', 'Pb208c', 'Pb208r', 'Pb208r_std', 'Pb208sample', 'Pb208sample_std', 'Pb_R45m', 'Pb_R45m_error_pct_1s', 'Pb_R46m', 'Pb_R46m_error_pct_1s', 'Pb_R65m', 'Pb_R65m_error_pct_1s', 'Pb_R75m', 'Pb_R75m_error_pct_1s', 'Pb_R76m', 'Pb_R76m_error_pct_1s', 'Pb_R84m_std', 'Pb_R84sample', 'Pb_R84sample_error_pct_2s', 'Pb_R85m', 'Pb_R85m_error_pct_1s', 'Pb_R86sample', 'Pb_R86sample_error_pct_2s', 'Pb_ppm', 'Pbc_pg', 'Pbr_Pbc', 'Pbr_pg', 'R46s', 'R46s_error_pct_2s', 'R54s', 'R54s_error_pct_2s', 'R64fc', 'R64s', 'R64s_error_pct_2s', 'R68r', 'R68r_Th', 'R68r_Th_error_pct_2s', 'R68r_error_pct_2s', 'R74s', 'R74s_error_pct_2s', 'R75r', 'R75r_Th', 'R75r_Th_error_pct_2s', 'R75r_error_pct_2s', 'R76r', 'R76r_Th', 'R76r_Th_error_pct_2s', 'R76r_error_pct_2s', 'R76s', 'R76s_error_pct_2s', 'R84s', 'R84s_error_pct_2s', 'R86rad', 'R86s', 'R86s_error_pct_2s', 'Th232s', 'Th_U', 'Th_ppm', 'U235s', 'U235s_std', 'U238s', 'U238s_std', 'U_R35m', 'U_R35m_error_pct_1s', 'U_R83m', 'U_R83m_error_pct_1s', 'U_R85m', 'U_R85m_error_pct_1s', 'U_ppm', 'mol_fraction_206r', 'rho_7568_r', 'rho_7646_s', 'rho_8646_s', 'rho_8676_r', 'rho_8676_s', 'rho_Pb8464sample', 't68', 't68_Th_corr', 't68_Th_corr_std', 't68_std', 't75', 't75_std', 't76', 't76_Th_corr', 't76_Th_corr_std', 't76_std'),
         ('E:t1', 'F:t2', 'G:t3', 'H:t4', 'I:t5', 'J:t6', 'K:t7', 'L:t8', 'M:t9')),
        ('output_table', 1,
         ('Pb206r_scaled', 'Pb_R84sample', 'Pb_R84sample_error_pct_2s', 'Pb_ppm', 'Pbc_export', 'Pbr_Pbc', 'R46s', 'R46s_error_pct_2s', 'R54s', 'R54s_error_pct_2s', 'R64fc', 'R68r_Th', 'R68r_Th_error_pct_2s', 'R75r', 'R75r_error_pct_2s', 'R76r_Th', 'R76r_Th_error_pct_2s', 'R76s', 'R76s_error_pct_2s', 'R84s', 'R84s_error_pct_2s', 'R86rad', 'R86s', 'R86s_error_pct_2s', 'Th_U', 'U_ppm', 'mol_fraction_206r', 'rho_5474_s', 'rho_7464_s', 'rho_7568_r', 'rho_7646_s', 'rho_8464_s', 'rho_8646_s', 'rho_8676_s', 'rho_Pb8464sample', 't68_Th_corr', 't68_Th_corr_std', 't75', 't75_std', 't76_Th_corr', 't76_Th_corr_std'),
         ('E:t1', 'F:t2', 'G:t3', 'H:t4', 'I:t5', 'J:t6', 'K:t7', 'L:t8', 'M:t9')),
        ('output_table', 2,
         ('R74s', 'R74s_error_pct_2s'),
         ('E:t1', 'F:t2', 'G:t3', 'H:t4', 'I:t5', 'J:t6', 'K:t7', 'L:t8', 'M:t9')),
        ('output_table', 3,
         ('R64s', 'R64s_error_pct_2s'),
         ('E:t1', 'F:t2', 'G:t3', 'H:t4', 'I:t5', 'J:t6', 'K:t7', 'L:t8', 'M:t9')),
    ],
    'new-all-Willsboro-gt-cpx_UPbR22XML.xls': [
        ('csv', 1,
         ('Pb206r_scaled', 'Pb_ppm', 'Pbc_export', 'Pbr_Pbc', 'R46s', 'R46s_error_pct_2s', 'R64fc', 'R68r_Th', 'R68r_Th_error_pct_2s', 'R75r', 'R75r_error_pct_2s', 'R76r_Th', 'R76r_Th_error_pct_2s', 'R76s', 'R76s_error_pct_2s', 'R86rad', 'R86s', 'R86s_error_pct_2s', 'Th_U', 'U_ppm', 'mol_fraction_206r', 'rho_7568_r', 'rho_7646_s', 'rho_8646_s', 'rho_8676_s', 't68_Th_corr', 't68_Th_corr_std', 't75', 't75_std', 't76_Th_corr', 't76_Th_corr_std'),
         ('X:g1', 'Y:g2', 'Z:g3', 'AA:g4', 'AB:g5', 'AC:g6', 'AD:g7', 'AE:g8')),
        ('engine', 1,
         ('FPb', 'FPb_std', 'FU', 'FU_std', 'Pb204b', 'Pb204c', 'Pb204c_std', 'Pb206b', 'Pb206c', 'Pb206r', 'Pb206r_std', 'Pb206s', 'Pb206s_std', 'Pb207b', 'Pb207c', 'Pb207r', 'Pb207r_std', 'Pb207s', 'Pb207s_std', 'Pb208b', 'Pb208c', 'Pb208r', 'Pb208r_std', 'Pb208sample', 'Pb208sample_std', 'Pb_R45m', 'Pb_R45m_error_pct_1s', 'Pb_R46m', 'Pb_R46m_error_pct_1s', 'Pb_R65m', 'Pb_R65m_error_pct_1s', 'Pb_R75m', 'Pb_R75m_error_pct_1s', 'Pb_R76m', 'Pb_R76m_error_pct_1s', 'Pb_R84m_std', 'Pb_R84sample', 'Pb_R84sample_error_pct_2s', 'Pb_R85m', 'Pb_R85m_error_pct_1s', 'Pb_R86sample', 'Pb_R86sample_error_pct_2s', 'Pb_ppm', 'Pbc_pg', 'Pbr_Pbc', 'Pbr_pg', 'R46s', 'R46s_error_pct_2s', 'R54s', 'R54s_error_pct_2s', 'R64fc', 'R64s', 'R64s_error_pct_2s', 'R68r', 'R68r_Th', 'R68r_Th_error_pct_2s', 'R68r_error_pct_2s', 'R74s', 'R74s_error_pct_2s', 'R75r', 'R75r_Th', 'R75r_Th_error_pct_2s', 'R75r_error_pct_2s', 'R76r', 'R76r_Th', 'R76r_Th_error_pct_2s', 'R76r_error_pct_2s', 'R76s', 'R76s_error_pct_2s', 'R84s', 'R84s_error_pct_2s', 'R86rad', 'R86s', 'R86s_error_pct_2s', 'Th232s', 'Th_U', 'Th_ppm', 'U235s', 'U235s_std', 'U238s', 'U238s_std', 'U_R35m', 'U_R35m_error_pct_1s', 'U_R83m', 'U_R83m_error_pct_1s', 'U_R85m', 'U_R85m_error_pct_1s', 'U_ppm', 'mol_fraction_206r', 'rho_7568_r', 'rho_7646_s', 'rho_8646_s', 'rho_8676_r', 'rho_8676_s', 'rho_Pb8464sample', 't68', 't68_Th_corr', 't68_Th_corr_std', 't68_std', 't75', 't75_std', 't76', 't76_Th_corr', 't76_Th_corr_std', 't76_std'),
         ('E:g1', 'F:g2', 'G:g3', 'H:g4', 'I:g5a', 'J:g5b', 'K:g6', 'L:g6 FD', 'M:d1', 'N:d2', 'O:d3', 'P:d4', 'Q:g1', 'R:g2', 'S:g3', 'T:g4', 'U:g5', 'V:g6', 'W:g7', 'X:g1', 'Y:g2', 'Z:g3', 'AA:g4', 'AB:g5', 'AC:g6', 'AD:g7', 'AE:g8', 'AF:TPB-g1', 'AG:TPB-g2', 'AH:TPB-g3')),
        ('output_table', 1,
         ('Pb206r_scaled', 'Pb_R84sample', 'Pb_R84sample_error_pct_2s', 'Pb_ppm', 'Pbc_export', 'Pbr_Pbc', 'R46s', 'R46s_error_pct_2s', 'R54s', 'R54s_error_pct_2s', 'R64fc', 'R68r_Th', 'R68r_Th_error_pct_2s', 'R75r', 'R75r_error_pct_2s', 'R76r_Th', 'R76r_Th_error_pct_2s', 'R76s', 'R76s_error_pct_2s', 'R84s', 'R84s_error_pct_2s', 'R86rad', 'R86s', 'R86s_error_pct_2s', 'Th_U', 'U_ppm', 'mol_fraction_206r', 'rho_5474_s', 'rho_7464_s', 'rho_7568_r', 'rho_7646_s', 'rho_8464_s', 'rho_8646_s', 'rho_8676_s', 'rho_Pb8464sample', 't68_Th_corr', 't68_Th_corr_std', 't75', 't75_std', 't76_Th_corr', 't76_Th_corr_std'),
         ('E:g1', 'F:g2', 'G:g3', 'H:g4', 'I:g5a', 'J:g5b', 'K:g6', 'L:g6 FD', 'M:d1', 'N:d2', 'O:d3', 'P:d4', 'Q:g1', 'R:g2', 'S:g3', 'T:g4', 'U:g5', 'V:g6', 'W:g7', 'X:g1', 'Y:g2', 'Z:g3', 'AA:g4', 'AB:g5', 'AC:g6', 'AD:g7', 'AE:g8', 'AF:TPB-g1', 'AG:TPB-g2', 'AH:TPB-g3')),
        ('output_table', 2,
         ('R74s', 'R74s_error_pct_2s'),
         ('E:g1', 'F:g2', 'G:g3', 'H:g4', 'I:g5a', 'J:g5b', 'K:g6', 'L:g6 FD', 'M:d1', 'N:d2', 'O:d3', 'P:d4', 'Q:g1', 'R:g2', 'S:g3', 'T:g4', 'U:g5', 'V:g6', 'W:g7', 'X:g1', 'Y:g2', 'Z:g3', 'AA:g4', 'AB:g5', 'AC:g6', 'AD:g7', 'AE:g8', 'AF:TPB-g1', 'AG:TPB-g2', 'AH:TPB-g3')),
        ('output_table', 3,
         ('R64s', 'R64s_error_pct_2s'),
         ('E:g1', 'F:g2', 'G:g3', 'H:g4', 'I:g5a', 'J:g5b', 'K:g6', 'L:g6 FD', 'M:d1', 'N:d2', 'O:d3', 'P:d4', 'Q:g1', 'R:g2', 'S:g3', 'T:g4', 'U:g5', 'V:g6', 'W:g7', 'X:g1', 'Y:g2', 'Z:g3', 'AA:g4', 'AB:g5', 'AC:g6', 'AD:g7', 'AE:g8', 'AF:TPB-g1', 'AG:TPB-g2', 'AH:TPB-g3')),
    ],
}

EXPECTED_AUXILIARY_FRACTIONS = {
    'SJ1_apatite_TIMS.csv': ('a1', 'a2', 'a3', 'a4', 'a5'),
    'ET2000Ma_solution.xls': ('2.0', '3.0', '5.0', '6.0', '10.0', '16.0', '18.0', '19.0', '13.0', '14.0', '15.0', '23.0', '17.0', '18.0', '19.0', '20.0', '23.0', '24.0', '25.0', '28 ', '30'),
}

EXPECTED_AUXILIARY_FAILURES = {
    'SJ1_apatite_TIMS.csv': [
        ('f', 'unknown', 't68_Th_corr', ('a1', 'a2', 'a3', 'a4', 'a5')),
        ('f', 'unknown', 't68_Th_corr_std', ('a1', 'a2', 'a3', 'a4', 'a5')),
        ('f', 'unknown', 't76_Th_corr', ('a1', 'a2', 'a3', 'a4', 'a5')),
    ],
    'ET2000Ma_solution.xls': [
        ('f', 'unknown', 't68_Th_corr_std', ('10.0', '13.0', '14.0', '15.0', '16.0', '17.0', '18.0', '19.0', '2.0', '20.0', '23.0', '24.0', '25.0', '28 ', '3.0', '30', '5.0', '6.0')),
        ('f', 'unknown', 't76_Th_corr_std', ('23.0', '5.0')),
    ],
}


@pytest.fixture(scope="module")
def audit():
    pytest.importorskip("xlrd", reason="read-only legacy audit needs optional xlrd")
    pytest.importorskip("openpyxl", reason="external common-Pb reference needs openpyxl")
    folder = Path(os.environ.get("IDTIMS_ADIRONDACK_DIR",
                                Path.home() / "Github/Adirondack_mountains/data/geochron_new/TIMS"))
    if not folder.is_dir():
        pytest.skip("private Adirondack TIMS folder absent; set IDTIMS_ADIRONDACK_DIR")
    tool_path = Path(__file__).resolve().parents[1] / "tools/audit_bsu_legacy.py"
    spec = importlib.util.spec_from_file_location("tools.audit_bsu_legacy", tool_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.run_audit(folder)


def test_live_workbook_categories(audit):
    assert {Path(w["source"]).name for w in audit["workbooks"]} == set(EXPECTED_FAILURES)
    for workbook in audit["workbooks"]:
        name = Path(workbook["source"]).name
        assert tuple(g["uid"] for g in workbook["grains"]) == EXPECTED_FRACTIONS[name]
        expected, actual, coverage = set(), set(), Counter()
        for source, cause_class, cause, quantities, fractions in EXPECTED_FAILURES[name]:
            expected.update((uid, source, quantity, cause_class, cause)
                            for uid in fractions for quantity in quantities)
        for grain in workbook["grains"]:
            for check in grain["checks"]:
                source = check.get("source", "engine")
                coverage[(grain["uid"], source, check["quantity"])] += 1
                if check["status"] == "MISMATCH":
                    actual.add((grain["uid"], source, check["quantity"],
                                check["cause_class"], check["cause"]))
        expected_coverage = {(uid, source, quantity): multiplicity
                             for source, multiplicity, quantities, fractions in EXPECTED_CHECK_COUNTS[name]
                             for uid in fractions for quantity in quantities}
        assert coverage == expected_coverage, name
        assert actual == expected, (name, "new failures", sorted(actual - expected),
                                    "resolved/reclassified failures", sorted(expected - actual))
    assert all(s["unchanged"] for s in audit["source_integrity"].values())


def test_fixed_engine_classes_reproduce_sheet_central_values(audit):
    for workbook in audit["workbooks"]:
        for record in workbook["grains"]:
            if record["diagnostic"] != "reduced":
                continue
            grain = record["_grain"]
            native = {c["quantity"]: c for c in record["checks"] if not c.get("source")}
            if native["Pb204c"]["sheet"] == 0:
                for quantity in ("Pb204c", "R46s", "R54s", "R64s", "R74s", "R84s"):
                    assert native[quantity]["engine"] == 0.0, (record["uid"], quantity)
                    assert native[quantity]["status"] == "exact", (record["uid"], quantity)
                for name in ("rho_8464_s", "rho_5474_s", "rho_8676_s", "rho_8646_s",
                             "rho_7464_s", "rho_7646_s"):
                    assert -1 <= getattr(grain, name) <= 1, (record["uid"], name)
            if record["settings"]["th"]["Th230_correction_type"] == "magma":
                for quantity in ("t68_Th_corr", "R68r_Th", "R76r_Th"):
                    assert native[quantity]["status"] == "exact", (record["uid"], quantity)


def test_reduced_only_reference_categories(audit):
    assert {Path(w["source"]).name for w in audit["auxiliary"]} == set(EXPECTED_AUXILIARY_FRACTIONS)
    for item in audit["auxiliary"]:
        name = Path(item["source"]).name
        assert tuple(g["fraction"] for g in item["grains"]) == EXPECTED_AUXILIARY_FRACTIONS[name]
        for grain in item["grains"]:
            assert {c["quantity"] for c in grain["checks"]} == {
                "t68_Th_corr", "t68_Th_corr_std", "t75", "t75_std", "t76_Th_corr", "t76_Th_corr_std"}
        expected = {(fraction, quantity, cause_class, cause)
                    for cause_class, cause, quantity, fractions in EXPECTED_AUXILIARY_FAILURES[name]
                    for fraction in fractions}
        actual = {(g["fraction"], c["quantity"], c["cause_class"], c["cause"])
                  for g in item["grains"] for c in g["checks"] if c["status"] == "MISMATCH"}
        assert actual == expected, (name, "new", actual - expected, "resolved", expected - actual)
        assert all(g["checks"] for g in item["grains"])


def test_strict_refusals_and_formula_interventions(audit):
    for workbook in audit["workbooks"]:
        for grain in workbook["grains"]:
            assert grain["strict"]["accepted"] is False, grain["uid"]
            assert grain["strict"]["reason"]
            if grain["diagnostic"] == "reduced":
                checks = {c["quantity"]: c for c in grain["checks"] if not c.get("source")}
                for quantity, interventions in grain["formula_experiments"].items():
                    if quantity in checks and "cached_formula_replay" in interventions:
                        assert interventions["cached_formula_replay"] == pytest.approx(
                            checks[quantity]["sheet"], rel=1e-10, abs=1e-30), (grain["uid"], quantity)
    for item in audit["auxiliary"]:
        for grain in item["grains"]:
            for check in grain["checks"]:
                if check.get("conditional_pairing"):
                    assert check["conditional_pairing"]["status"] != "MISMATCH", grain["fraction"]

