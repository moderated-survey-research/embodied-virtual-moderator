# imports
import pandas as pd, numpy as np

from IPython.display import display
import matplotlib.pyplot as plt
import seaborn as sns

import math, re, os, json
from dotenv import load_dotenv

from wordfreq import word_frequency
from nltk.sentiment import SentimentIntensityAnalyzer
from symspellpy.symspellpy import SymSpell

from scipy.stats import shapiro, chi2_contingency, mannwhitneyu, kruskal, levene, spearmanr
from scikit_posthocs import posthoc_nemenyi
import statsmodels.formula.api as smf
import statsmodels.api as sm

from openai import OpenAI
import io

rng = np.random.default_rng(42)

# loading ENV
load_dotenv()
API = os.getenv("API")
DICTIONARY_PATH = os.getenv("DICTIONARY_PATH")

# CONSTANTS
VARIANTS = ['bfi2s_avatar', 'bfi2s_classic', 'cfq_avatar', 'cfq_classic']
TYPES = ['avatar', 'classic']
FORMS = ['bfi', 'cfq']

# method definitions
# def mannEffSize(U, n1, n2):
#     n = n1+n2
#     z = (U - ((n1*n2)/2)) / np.sqrt((n1*n2*(n1+n2+1)) / (12))
#     #print('z:', z)
#     r = np.abs(z) / np.sqrt(n1+n2)
#     #print('r:', r)
#     return z, r

def kruEffSize(H, n, k):
    eta = (H - k + 1)/(n - k)
    #print('eta:', eta)
    return eta

def chiEffSize(chi, n, k, table=None):
    v = np.sqrt(chi/(n*(k-1)))
    #print('V:', v)

    def cramers_v_from_table(tab):
        chi2, _, _, _ = chi2_contingency(tab, correction=False)
        n = tab.sum()
        k = min(tab.shape)
        return np.sqrt(chi2 / (n * (k - 1)))

    try:
        table = np.array(table)
        N = table.sum()
        p = table / N
        V_boot = np.empty(5000)
        for b in range(5000):
            flat = np.random.multinomial(N, p.ravel()).reshape(table.shape)
            if flat.sum(axis=1).min()==0 or flat.sum(axis=0).min()==0:
                V_boot[b] = np.nan
            else:
                V_boot[b] = cramers_v_from_table(flat)
        V_boot = V_boot[~np.isnan(V_boot)]
        V_L, V_U = np.percentile(V_boot, [2.5, 97.5])
    except:
        V_L, V_U = (np.nan, np.nan)

    return v, (V_L, V_U)

def mannwhitney_z_r(U, x1, x2, continuity=True):
    n1, n2 = len(x1), len(x2)
    combined = np.concatenate([x1, x2])
    
    _, counts = np.unique(combined, return_counts=True)
    tie_correction = np.sum(counts**3 - counts)
    N = n1 + n2

    mean_U = n1 * n2 / 2
    sd_U = np.sqrt(
        (n1 * n2 / 12) *
        ((N + 1) - tie_correction / (N * (N - 1)))
    )

    correction = 0.5 if continuity else 0
    if U < mean_U:
        z = (U - mean_U + correction) / sd_U
    else:
        z = (U - mean_U - correction) / sd_U

    r = z / np.sqrt(N)

    ps = U / (n1 * n2)
    
    ps_bs = []
    r_boot = []
    for _ in range(5000):
        xb = rng.choice(x1, size=n1, replace=True)
        yb = rng.choice(x2, size=n2, replace=True)
        Ub = mannwhitneyu(xb, yb, alternative='two-sided').statistic
        ps_bs.append(Ub / (n1 * n2))
        mean_Ub = n1 * n2 / 2
        sd_Ub = np.sqrt(
            (n1 * n2 / 12) *
            ((N + 1) - tie_correction / (N * (N - 1)))
        )
        z_b = (Ub - mean_Ub) / sd_Ub
        r_boot.append(z_b / np.sqrt(N))
    lo, hi = np.percentile(ps_bs, [100*0.05/2, 100*(1-0.05/2)])
    lo_r, hi_r = np.percentile(r_boot, [100*0.05/2, 100*(1-0.05/2)])
        
    return z, r, (lo_r, hi_r), ps, (lo, hi)


def EDA(data, groupby, attribute):
    display(data.groupby(groupby)[attribute].agg(['mean', 'std']))
    display(pd.DataFrame(data.groupby(groupby)[attribute].quantile([0, 0.25, 0.5, 0.75, 1])).unstack())

def EDAPLOT(data, groupby, attribute):
    sns.boxplot(data, x=attribute, hue=groupby, showfliers=False)
    plt.show()

def ANALYSISPAIR(data, groupby, attribute, customID = False):
    groups = data[groupby].unique()
    print(groups)

    if(not customID):
        customID = 'respondentID'

    samples = [data[data[groupby]==x].groupby(customID)[attribute].median() for x in groups]
    samples2 = [data[data[groupby]==x].groupby(customID)[attribute].mean() for x in groups]

    for i in samples:
        print(np.round(shapiro(i)[1], 4), ' ', end='')
    print("\n")

    print(groups[0]+ ": M={}, SD={}, MED={}, IQR=({}-{})".format(
        np.round(samples[0].mean(), 2), 
        np.round(samples[0].std(), 2),
        np.round(samples[0].median(), 2),
        np.round(samples[0].quantile(0.25), 2),
        np.round(samples[0].quantile(0.75), 2)
    ))
    print(groups[1]+ ": M={}, SD={}, MED={}, IQR=({}-{})".format(
        np.round(samples[1].mean(), 2), 
        np.round(samples[1].std(), 2),
        np.round(samples[1].median(), 2),
        np.round(samples[1].quantile(0.25), 2),
        np.round(samples[1].quantile(0.75), 2)
    ))
    print()
    
    print('median')
    stat, p = mannwhitneyu(*samples)
    n1 = len(samples[0])
    n2 = len(samples[1])
    z, r, (l_r, h_r), ps, (l, h) = mannwhitney_z_r(stat, samples[0], samples[1])
    print("U({})={}, z={}, p={}, r={} [{}, {}], ps={} [{}, {}]".format(n1+n2, np.round(stat, 2), np.round(z, 2), np.round(p, 4), np.round(r, 2), np.round(l_r, 2), np.round(h_r, 2), np.round(ps, 2), np.round(l, 2), np.round(h, 2)))
    print()

    print('median', groups[0], '<', groups[1])
    stat, p = mannwhitneyu(samples[0], samples[1], alternative="less")
    n1 = len(samples[0])
    n2 = len(samples[1])
    print("U({})={}, p={}".format(n1+n2, stat, p))
    mannwhitney_z_r(stat, samples[0], samples[1])
    print()

    print('median', groups[0], '>', groups[1])
    stat, p = mannwhitneyu(samples[0], samples[1], alternative="greater")
    n1 = len(samples[0])
    n2 = len(samples[1])
    print("U({})={}, p={}".format(n1+n2, stat, p))
    mannwhitney_z_r(stat, samples[0], samples[1])
    print()

    print('variance')
    stat, p = levene(samples[0], samples[1], center='median')
    n1 = len(samples[0])
    n2 = len(samples[1])
    print("F(1, {})={}, p={}".format(n1+n2, np.round(stat, 2), np.round(p, 4)))
    print()

    print('mean')
    stat, p = mannwhitneyu(*samples2)
    n1 = len(samples[0])
    n2 = len(samples[1])
    print("U({})={}, p={}".format(n1+n2, stat, p))
    mannwhitney_z_r(stat, samples[0], samples[1])
    print()

    print('no aggregation')
    samples = [data[data[groupby]==x][attribute].values for x in groups]
    stat, p = mannwhitneyu(*samples)
    n1 = len(samples[0])
    n2 = len(samples[1])
    print("U({})={}, p={}".format(n1+n2, stat, p))
    mannwhitney_z_r(stat, samples[0], samples[1])
    print()

    # normalita nie je problem ak je sample size velka a ak nas zaujima hlavne p value
    model = smf.mixedlm(
        formula=attribute + " ~ " + groupby,
        data=data,
        groups=data[customID],
        re_formula="1"  
    )
    result = model.fit()
    print(result.summary())
    print(shapiro(result.resid)[1])

def ANALYSISMULTIPLE(data, groupby, attribute, customOrder = False, customID = False):
    groups = data[groupby].unique()
    print(groups)

    if(not customID):
        customID = 'respondentID'

    samples = [data[data[groupby]==x].groupby(customID)[attribute].median() for x in groups]

    for i in samples:
        print(np.round(shapiro(i)[1], 4), ' ', end='')
    print("\n")

    stat, p = kruskal(*samples)
    n = sum([len(x) for x in samples])
    print("H({})={}, p={}".format(n, stat, p))
    kruEffSize(stat, n, len(samples))
    print(posthoc_nemenyi(samples))
    print()

    samples = [data[data[groupby]==x][attribute].values for x in data[groupby].unique()]
    stat, p = kruskal(*samples)
    n = sum([len(x) for x in samples])
    print("H({})={}, p={}".format(n, stat, p))
    kruEffSize(stat, n, len(samples))
    print(posthoc_nemenyi(samples))
    print()

    if(customOrder):
        data[groupby] = pd.Categorical(data[groupby], categories=customOrder, ordered=False)
    model = smf.mixedlm(
        formula=attribute + " ~ " + groupby,
        data=data,
        groups=data[customID],
        re_formula="1"  
    )
    result = model.fit()
    print(result.summary())
    
    print(shapiro(result.resid)[1])

def EDACATS(data, groupby, attribute):
    display(data.groupby(groupby)[attribute].value_counts().unstack())
    display(data.groupby(groupby)[attribute].agg(['mean', 'std', 'median']))

def ANALYSISCATS(data, groupby, attribute, customID = False):
    if(not customID):
        customID = 'respondentID'

    table = data.groupby(groupby)[attribute].value_counts().unstack()
    
    groups = data[groupby].unique()
    print(groups)
    
    #temp = data[[customID, groupby, attribute]].groupby([customID, groupby]).mean().reset_index()
    samples = [data[data[groupby]==x].groupby(customID)[attribute].mean() for x in groups]

    for i in samples:
        print(np.round(shapiro(i)[1], 4), ' ', end='')
    print("\n")

    print(groups[0]+ ": M={}, SD={}, MED={}, IQR=({}-{})".format(
        np.round(samples[0].mean(), 2), 
        np.round(samples[0].std(), 2),
        np.round(samples[0].median(), 2),
        np.round(samples[0].quantile(0.25), 2),
        np.round(samples[0].quantile(0.75), 2)
    ))
    print(groups[1]+ ": M={}, SD={}, MED={}, IQR=({}-{})".format(
        np.round(samples[1].mean(), 2), 
        np.round(samples[1].std(), 2),
        np.round(samples[1].median(), 2),
        np.round(samples[1].quantile(0.25), 2),
        np.round(samples[1].quantile(0.75), 2)
    ))
    print()

    if(len(samples)==2):

        print('mean')
        stat, p = mannwhitneyu(*samples)
        n1 = len(samples[0])
        n2 = len(samples[1])
        z, r, (l_r, h_r), ps, (l, h) = mannwhitney_z_r(stat, samples[0], samples[1])
        print("U({})={}, z={}, p={}, r={} [{}, {}], ps={} [{}, {}]".format(n1+n2, np.round(stat, 2), np.round(z, 2), np.round(p, 4), np.round(r, 2), np.round(l_r, 2), np.round(h_r, 2), np.round(ps, 2), np.round(l, 2), np.round(h, 2)))
        print()

        print('mean', groups[0], '<', groups[1])
        stat, p = mannwhitneyu(samples[0], samples[1], alternative="less")
        n1 = len(samples[0])
        n2 = len(samples[1])
        print("U({})={}, p={}".format(n1+n2, stat, p))
        mannwhitney_z_r(stat, samples[0], samples[1])
        print()

        print('mean', groups[0], '>', groups[1])
        stat, p = mannwhitneyu(samples[0], samples[1], alternative="greater")
        n1 = len(samples[0])
        n2 = len(samples[1])
        print("U({})={}, p={}".format(n1+n2, stat, p))
        mannwhitney_z_r(stat, samples[0], samples[1])
        print()

        print('variance')
        stat, p = levene(samples[0], samples[1], center='median')
        n1 = len(samples[0])
        n2 = len(samples[1])
        print("F(1, {})={}, p={}".format(n1+n2, stat, p))
        print()

    print('no aggregation')
    stat, p, d, exp = chi2_contingency(table)
    n = np.sum(np.matrix(table))
    print("X({}, d = {}) = {}, p = {}".format(n, d, stat, p))
    print(chiEffSize(stat, n, min(table.shape), table))
    print()
    print(table.div(table.sum(axis=1), axis=0))

def EDACATSPLOT(data, groupby, attribute, customID = False):
    if(not customID):
        customID = 'respondentID'
    
    data.groupby(groupby)[attribute].value_counts().unstack().plot(kind='bar')
    plt.show()

    sns.boxplot(
        data.groupby([customID, groupby])[attribute].mean().reset_index(),
        x=groupby,
        y=attribute,
        showfliers=False
    )
    plt.show()
