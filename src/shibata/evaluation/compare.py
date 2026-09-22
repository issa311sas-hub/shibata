"""Compare model and market on identical rows using existing v1 definitions."""
from .baseline import evaluate_observed_results
from ..ingestion.contracts import require

SCORES=('binary_log_loss_per_runner','binary_brier_per_runner',
        'winner_log_loss_per_race','multiclass_brier_per_race')


def compare(model_predictions,market_predictions,results):
    key=['race_id','horse_id']
    require(set(model_predictions.columns)>=set(key+['probability']),'Missing model probabilities')
    require(not model_predictions.duplicated(key).any(),'Duplicate model predictions')
    require(set(map(tuple,model_predictions[key].to_numpy()))==
            set(map(tuple,market_predictions[key].to_numpy())), 'Model/market population mismatch')
    market_metrics,market_tables=evaluate_observed_results(market_predictions,results)
    joined=market_predictions.drop(columns=['market_probability']).merge(
        model_predictions[key+['probability']],on=key,validate='one_to_one')
    # Adapt the legacy metric input column only; formulas and grouping are unchanged.
    model_metrics,model_tables=evaluate_observed_results(
        joined.rename(columns={'probability':'market_probability'}),results)
    return dict(market=market_metrics,model=model_metrics,
                model_minus_market={name:model_metrics[name]-market_metrics[name] for name in SCORES},
                comparison_scope='exact same race/horse population and market grouping',
                performance_claim='descriptive comparison only; requires experiment provenance'),dict(market=market_tables,model=model_tables)
