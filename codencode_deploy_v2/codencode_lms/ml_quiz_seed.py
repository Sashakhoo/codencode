"""Machine Learning checkpoint quizzes (10 easy MCQs each): Week 4 covers
Weeks 1-4 (Feature Engineering, Intro to ML, Regression, Classification) and
Week 7 covers Weeks 1-7 (a few Weeks 1-4 questions, different ones than the
Week 4 quiz uses, plus Neural Networks, LSTM & Time Series, and Ensembles &
Model Tuning). Written from the Session 01-07 slide decks. Each question:
(text, correct, [3 wrong], explanation). The correct answer is listed first
here and shuffled deterministically on seed - same format as quiz_seed_python.py."""

_WEEK4_QUESTIONS = [
    ('In a dataset, what is a "feature"?', 'One measurable input column, like size or price',
     ['The column you are trying to predict', 'One row of the dataset', 'The model itself'],
     'A feature is one column of input data. The column you predict is the target, not a feature.'),
    ('Why do models like KNN and neural networks need features to be scaled first?', 'A feature measured in big numbers would otherwise dominate, even if it does not matter more',
     ['Scaling makes the dataset smaller', 'Scaling removes missing values', 'Decision trees require it'],
     'Distance and gradient based models add features together, so unscaled big-unit columns unfairly dominate. Trees do not need scaling.'),
    ('Why is one-hot encoding usually safer than label encoding for a column like city?', 'Label encoding invents a false order (e.g. implies Ipoh > Penang) that is not real',
     ['One-hot encoding is faster to compute', 'Label encoding cannot be used with pandas', 'One-hot encoding removes missing values'],
     'Mapping categories to 0,1,2,3 makes a model think one city is "greater than" another, which is not true for nominal categories.'),
    ('What is data leakage?', 'Information that would not be available at prediction time getting into training',
     ['A dataset with missing values', 'A model that trains too slowly', 'A feature with too many categories'],
     'Leakage makes a model look brilliant in testing and fail in production, because it secretly saw information it should not have had.'),
    ('Fitting a scaler on the WHOLE dataset before splitting into train and test is an example of...', 'Data leakage',
     ['Correct practice', 'Feature engineering', 'Underfitting'],
     'The scaler should only ever be fit on the training data, then applied to the test data - fitting on everything first leaks test information into training.'),
    ('What is the key question that tells you whether a problem is supervised?', 'Does a column in the data hold the correct answer?',
     ['Is the dataset very large?', 'Does the data have missing values?', 'Is the target measured in ringgit?'],
     'Supervised learning needs labelled examples - a column with the known correct answer. No such column means unsupervised.'),
    ('Why is data split into train, validation AND test sets, not just train and test?', 'The validation set lets you tune and compare models without touching the test set',
     ['It makes the dataset larger', 'Models train faster with three sets', 'Only classification needs three sets'],
     'The test set should be opened once, at the very end, to honestly estimate real-world performance - tuning happens on the validation set instead.'),
    ('A model scores 99% on training data but only 60% on test data. What is this?', 'Overfitting - it memorised the training data instead of learning the real pattern',
     ['Underfitting', 'Data leakage', 'A healthy, well-fit model'],
     'A big gap between training and test scores, with training much higher, is the classic sign of overfitting.'),
    ('What is the key difference between regression and classification?', 'Regression predicts a number; classification predicts a category',
     ['Regression is always more accurate', 'Classification needs more data', 'Regression cannot use scikit-learn'],
     'Predicting a house price is regression (a continuous number); predicting spam or not spam is classification (a category).'),
    ('On a dataset where only 1% of cases are fraud, a model that always predicts "not fraud" scores 99% accuracy. Why is this a problem?', 'Accuracy hides that the model catches zero fraud cases - it is misleading on imbalanced data',
     ['It is not a problem - 99% accuracy is excellent', 'The model needs more training data only', 'Accuracy cannot be computed on imbalanced data'],
     'On imbalanced data, accuracy rewards ignoring the rare class entirely. Precision and recall on the minority class tell the real story.'),
]

_WEEK7_QUESTIONS = [
    # Four Weeks 1-4 recap questions - different facts than the Week 4 quiz above, so the two quizzes don't overlap.
    ('Ridge and Lasso both penalise large coefficients. What does Lasso do that Ridge does not?', 'Lasso can shrink weak features all the way to exactly zero, removing them',
     ['Lasso only works on classification problems', 'Ridge cannot be used with linear regression', 'Lasso requires no train/test split'],
     'Ridge shrinks every coefficient a little; Lasso keeps pushing weak ones until they hit exactly zero, which acts like automatic feature selection.'),
    ('In a confusion matrix, what does a "false negative" mean?', 'A real positive case that the model missed and did not flag',
     ['A case the model correctly flagged', 'A negative case that was correctly ignored', 'A case that was flagged but was actually negative'],
     'False negative = the real answer was positive (e.g. a customer who churned), but the model said negative and missed it.'),
    ('Why does a Random Forest usually generalise better than one single deep decision tree?', 'Many trees, trained on different random samples, average out each other’s individual quirks',
     ['A forest always trains faster than one tree', 'A forest never needs a train/test split', 'A single tree cannot be used for classification'],
     'A single deep tree can memorise noise in the rows it saw. Averaging many differently-trained trees cancels that noise while keeping the real signal.'),
    ('What is the purpose of a baseline model, like predicting the average or the most common class?', 'It gives you a minimum bar your real model must beat to prove it learned something',
     ['It is the model you should always ship', 'It removes the need for a test set', 'It only applies to time series data'],
     'If a tuned model cannot beat simply guessing the average or the majority class, it has not actually learned anything useful yet.'),
    # New Weeks 5-7 questions.
    ('What does a single neuron in a neural network compute?', 'A weighted sum of its inputs, plus a bias, passed through an activation function',
     ['A full decision tree', 'A random sample of the training data', 'The final prediction with no further steps'],
     'z = weighted sum + bias, then a = f(z) is the activation. Stacking many of these is what makes a neural network.'),
    ('When training a neural network, which curve actually tells you whether it is learning something useful?', 'The validation loss curve',
     ['The training loss curve', 'The number of epochs', 'The batch size'],
     'Training loss falls forever whether or not the model is learning anything that generalises - only validation loss reveals the truth.'),
    ('When splitting a time series into train and test sets, what is the correct approach?', 'Split by date - all training rows must come before all test rows in time',
     ['Split randomly, like any other dataset', 'Put the most recent data in training', 'Shuffle first, then split 80/20'],
     'A random split would let the model "see the future" during training, producing a score that looks great but is fiction.'),
    ('Why do plain RNNs struggle to remember information from many steps earlier?', 'The vanishing gradient - the error shrinks a little at every step travelling backward, until it is nearly zero',
     ['They do not use enough neurons', 'They only work on images', 'They always overfit immediately'],
     'After enough steps the gradient has shrunk to almost nothing, so early information barely influences training. LSTM gates were built to fix this.'),
    ('What is the main difference between bagging (like Random Forest) and boosting (like XGBoost)?', 'Bagging trains models in parallel and averages them; boosting trains models in sequence, each correcting the last',
     ['Bagging only works on images; boosting only works on tables', 'Boosting cannot be used for classification', 'Bagging requires a GPU and boosting does not'],
     'Bagging reduces variance by averaging independent models. Boosting reduces bias by having each new model fix what the previous ones got wrong.'),
    ('Why should every preprocessing step (scaling, encoding, imputing) be placed inside a scikit-learn Pipeline?', 'It makes it structurally impossible for a step to accidentally be fit on the test data, preventing leakage',
     ['It makes the model train faster', 'It is required before you can use XGBoost', 'It automatically improves accuracy'],
     'A big gap between cross-validation score and test score usually means something was fitted where it should not have been - a Pipeline prevents that by construction.'),
]

ML_QUIZZES = [
    {
        'week': 4,
        'title': 'ML Week 4 Quiz — Weeks 1 to 4 Review',
        'description': 'Checkpoint on Feature Engineering, Intro to Machine Learning, Regression Models and Classification.',
        'questions': _WEEK4_QUESTIONS,
    },
    {
        'week': 7,
        'title': 'ML Week 7 Quiz — Weeks 1 to 7 Review',
        'description': 'Checkpoint covering everything through Week 7, including Neural Networks, LSTM & Time Series, and Ensembles & Model Tuning.',
        'questions': _WEEK7_QUESTIONS,
    },
]

assert all(len(q['questions']) == 10 for q in ML_QUIZZES), 'each ML quiz needs 10 questions'
for _q in ML_QUIZZES:
    assert len({t[0] for t in _q['questions']}) == 10, 'duplicate question inside an ML quiz'
assert not ({t[0] for t in ML_QUIZZES[0]['questions']} &
            {t[0] for t in ML_QUIZZES[1]['questions']}), 'Week 7 repeats a Week 4 question'
