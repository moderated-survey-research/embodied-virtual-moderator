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

# loading ENV
load_dotenv()
API = os.getenv("API")
DICTIONARY_PATH = os.getenv("DICTIONARY_PATH")

# CONSTANTS
VARIANTS = ['bfi2s_avatar', 'bfi2s_classic', 'cfq_avatar', 'cfq_classic']
TYPES = ['avatar', 'classic']
FORMS = ['bfi', 'cfq']

# method definitions
def mannEffSize(U, n1, n2):
    n = n1+n2
    z = (U - ((n1*n2)/2)) / np.sqrt((n1*n2*(n1+n2+1)) / (12))
    #print('z:', z)
    r = np.abs(z) / np.sqrt(n1+n2)
    #print('r:', r)
    return z, r

def kruEffSize(H, n, k):
    eta = (H - k + 1)/(n - k)
    #print('eta:', eta)
    return eta

def chiEffSize(chi, n, k):
    v = np.sqrt(chi/(n*(k-1)))
    #print('V:', v)
    return v


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
    z, r = mannEffSize(stat, n1, n2)
    print("U({})={}, z={}, p={}, r={}".format(n1+n2, np.round(stat, 2), np.round(z, 2), np.round(p, 4), np.round(r, 2)))
    print()

    print('median', groups[0], '<', groups[1])
    stat, p = mannwhitneyu(samples[0], samples[1], alternative="less")
    n1 = len(samples[0])
    n2 = len(samples[1])
    print("U({})={}, p={}".format(n1+n2, stat, p))
    mannEffSize(stat, n1, n2)
    print()

    print('median', groups[0], '>', groups[1])
    stat, p = mannwhitneyu(samples[0], samples[1], alternative="greater")
    n1 = len(samples[0])
    n2 = len(samples[1])
    print("U({})={}, p={}".format(n1+n2, stat, p))
    mannEffSize(stat, n1, n2)
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
    mannEffSize(stat, n1, n2)
    print()

    print('no aggregation')
    samples = [data[data[groupby]==x][attribute].values for x in groups]
    stat, p = mannwhitneyu(*samples)
    n1 = len(samples[0])
    n2 = len(samples[1])
    print("U({})={}, p={}".format(n1+n2, stat, p))
    mannEffSize(stat, n1, n2)
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
        z, r = mannEffSize(stat, n1, n2)
        print("U({})={}, z={}, p={}, r={}".format(n1+n2, np.round(stat, 2), np.round(z, 2), np.round(p, 4), np.round(r, 2)))
        print()

        print('mean', groups[0], '<', groups[1])
        stat, p = mannwhitneyu(samples[0], samples[1], alternative="less")
        n1 = len(samples[0])
        n2 = len(samples[1])
        print("U({})={}, p={}".format(n1+n2, stat, p))
        mannEffSize(stat, n1, n2)
        print()

        print('mean', groups[0], '>', groups[1])
        stat, p = mannwhitneyu(samples[0], samples[1], alternative="greater")
        n1 = len(samples[0])
        n2 = len(samples[1])
        print("U({})={}, p={}".format(n1+n2, stat, p))
        mannEffSize(stat, n1, n2)
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
    print(chiEffSize(stat, n, min(table.shape)))
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
