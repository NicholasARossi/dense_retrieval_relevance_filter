import numpy as np
from torcheval.metrics.functional import binary_auprc
from sklearn.metrics import precision_recall_curve
import os
import argparse
import json
import pandas as pd
import torch

def precision_and_threshold_at_recall(labels, scores, percentile=0.9):
    """
    get the precision/threshold when recall is at certain percentage
    """
    precision, recall, threshold = precision_recall_curve(labels, scores)
    idx = np.argmin(recall > percentile)
    return precision[idx], recall[idx], threshold[idx]

def compute_precision(labels, predictions, imputation=0):
    if sum(predictions):
        precision = sum(labels & predictions)/sum(predictions)
    else:
        precision = imputation
    return precision

def compute_metrics(df, df_label, k, score_column, apply_filter=False, percentile=0.9, use_all_data_for_cutoff=True):
    df = df.merge(df_label[['query','passage','relevance']], on = ['query','passage'], how='left')
    df['relevance'] = df['relevance'].fillna(0)
    df_k = df[df['rank']<=k]
    df = df[df['rank']<=100]

    # AUC, auc is computed before applying filters
    auc = binary_auprc(torch.tensor(df_k[score_column].values),
                       torch.tensor(df_k['relevance'].values))

    if apply_filter:
        if not use_all_data_for_cutoff:
            df = df_k
        precision, recall, threshold = precision_and_threshold_at_recall(
            df['relevance'].values, df[score_column].values, percentile)
        precision = compute_precision(df_k['relevance'] == 1, df_k[score_column]>threshold)
        removed_percentage = sum(df_k[score_column] < threshold) / len(df_k) * 100
        removed_positive_percentage = sum((df_k[score_column] < threshold) & (df_k['relevance']>0)) / len(df_k) * 100
        null_result_percentage = sum(df_k.groupby('query')[score_column].max() < threshold)/df_k['query'].nunique() * 100
        print(f'removed {removed_percentage: .2f}% docs, {removed_positive_percentage: .2f}% positive docs, {null_result_percentage: .2f}% queries have null results')
    else:
        # precision
        precision = df_k.groupby('query')['relevance'].apply(lambda x: sum(x==1)/len(x)).mean()
        # recall
        df_r = df_label[['query','passage','relevance']].merge(df_k[['query','passage','rank']], on = ['query','passage'], how='left')
        recall = df_r.groupby('query')['rank'].apply(lambda x: sum(x<=k)/len(x)).mean()

    if apply_filter:
        return {'k': k, 'precision': precision, 'recall': recall, 'auc': float(auc), 'threshold': threshold}
    else:
        return {'k': k, 'precision': precision, 'recall': recall, 'auc': float(auc)}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data_dir",
                        help="path to train directory",
                        default=None)
    parser.add_argument("--inference_output",
                        help="path to the inferene output file",
                        default=None)
    args = parser.parse_args()

    df_label = pd.read_csv(os.path.join(args.data_dir, 'dev_qrels.txt'), sep='\t', header=None, names=['query','0','passage','relevance'])
    df_adjusted = pd.read_json(args.inference_output, lines=True)
    df_adjusted.columns = ['query','passage', 'label', 'model_score', 'adjusted_score']
    df_adjusted['rank'] = df_adjusted.groupby('query')['model_score'].rank(method='min', ascending=False)
    output_file_path = args.inference_output.replace('results_test.json', 'metrics_test.json')
    f_out = open(output_file_path, 'w')

    for k in [10, 50, 100, 1000]:
        print('no filter')
        metrics = compute_metrics(df_adjusted, df_label, k, score_column='model_score', apply_filter=False)
        print(metrics)
        metrics['type'] = 'model_scores'
        f_out.write(json.dumps(metrics) + '\n')
        metrics = compute_metrics(df_adjusted, df_label, k, score_column='adjusted_score', apply_filter=False)
        print(metrics)
        metrics['type'] = 'adjusted scores'
        f_out.write(json.dumps(metrics) + '\n')
        print('recall = 99%')
        metrics = compute_metrics(df_adjusted, df_label, k, score_column='model_score', apply_filter=True, percentile=0.99)
        print(metrics)
        metrics['type'] = 'model scores w/ filter, p99'
        f_out.write(json.dumps(metrics) + '\n')
        metrics = compute_metrics(df_adjusted, df_label, k, score_column='adjusted_score', apply_filter=True, percentile=0.99)
        print(metrics)
        metrics['type'] = 'adjusted scores w/ filter, p99'
        f_out.write(json.dumps(metrics) + '\n')
        print('recall = 95%')
        print('adjusted scores w/ filter, p95')
        metrics = compute_metrics(df_adjusted, df_label, k, score_column='model_score', apply_filter=True, percentile=0.95)
        print(metrics)
        metrics['type'] = 'model scores w/ filter, p95'
        f_out.write(json.dumps(metrics) + '\n')
        metrics = compute_metrics(df_adjusted, df_label, k, score_column='adjusted_score', apply_filter=True, percentile=0.95)
        print(metrics)
        metrics['type'] = 'adjusted scores w/ filter, p95'
        f_out.write(json.dumps(metrics) + '\n')
    f_out.close()


if __name__ == '__main__':
    """
    python metrics.py --data_dir $DATA_DIR --inference_output $MODEL_DIR/results_test.json
    """
    main()
