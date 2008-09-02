#include <Python.h>

// NLP C module
#include "nlp.h"

static PyObject* maxent_log_probs(PyObject *self, PyObject *args) {
  PyObject *features, *weights, *labels;
  PyObject *label;
  Py_ssize_t i;
  int ok;

  if (!PyArg_ParseTuple(args, "OOO", &features, &weights, &labels))
    return NULL;

  // This is crap for testing - should see if weights is a countermap, not just a dict
  // (at min, check if values of weights are dicts)
  if (!PyDict_Check(features) || ! PyDict_Check(weights) || ! PyAnySet_Check(labels))
	// FIXME: Should be setting an exception here
	return NULL;

// log_probs = Counter()
  PyObject *log_probs = NlpCounter_New();

// for label in self.labels:
  i = 0;
  while (_PySet_Next(labels, &i, &label)) {
//   log_probs[label] = sum((weights[label] * datum_features).itervalues())
	PyObject *newValue;
	double sum = 0.0;
	Py_ssize_t j;
	PyObject *featureKey, *featureCount;
	PyObject *labelWeights = PyDict_GetItem(weights, label);;
	
	if (labelWeights) {
	  j = 0;
	  while (PyDict_Next((PyObject*)features, &j, &featureKey, &featureCount)) {
		PyObject *weight = PyDict_GetItem(labelWeights, featureKey);
		sum += PyFloat_AsDouble(featureCount) * PyFloat_AsDouble(weight);
	  }
	}

	newValue = PyFloat_FromDouble(sum);
	ok = PyDict_SetItem(log_probs, label, newValue);

	Py_DECREF(newValue);
	if (ok < 0) {
	  Py_DECREF(log_probs);
	  return NULL;
	}
  }

  // log_probs.log_normalize()
  NlpCounter_LogNormalize(log_probs);

  return log_probs;
}

static PyObject* maxent_expected_counts(PyObject *self, PyObject *args) {
  PyObject *labeled_extracted_features, *labels, *log_probs;
  PyObject *expected_counts;
  PyObject **label_counter_cache;
  
  // If we get passed a list, we convert it to a tuple and use this to XDECREF for cleanup
  PyObject *labeled_extracted_features_tuple = NULL;

  // Loop variables
  Py_ssize_t datum_index, label_index, num_datum, label_num;
  PyObject *label;

  if (!PyArg_ParseTuple(args, "OOOO", &labeled_extracted_features, &labels, &log_probs, &expected_counts))
	return NULL;

  if (PyList_Check(labeled_extracted_features)) {
	labeled_extracted_features = PyList_AsTuple(labeled_extracted_features);
	labeled_extracted_features_tuple = labeled_extracted_features;
  }

  if (!PyTuple_Check(labeled_extracted_features) || !PyAnySet_Check(labels) || !PyList_Check(log_probs) || !PyDict_Check(expected_counts)) {
	if (!PyTuple_Check(labeled_extracted_features)) printf("labeled_extracted_features\n");
	if (!PyAnySet_Check(labels)) printf("labels\n");
	if (!PyList_Check(log_probs)) printf("log_probs\n");
	if (!PyDict_Check(expected_counts)) printf("expected_counts\n");
	printf("Types suck\n");

	Py_XDECREF(labeled_extracted_features_tuple);
	PyErr_BadArgument();
	return NULL;
  }

  Py_INCREF(expected_counts);

  // Cache pointers to the label counters we're creating so we don't have to lookup every iteration of the inner loop
  // NOTE: playing fast and loose with references here to make things easier to cleanup
  label_counter_cache = (PyObject**)malloc(sizeof(PyObject*) * PySet_Size(labels));
  // This could be in the deeper loop, but removes a contains? call
  label_index = 0;
  label_num = 0;
  while (_PySet_Next(labels, &label_index, &label)) {
	PyObject *labelCounter = NlpCounter_New();
	int ok;

	ok = PyDict_SetItem(expected_counts, label, labelCounter);
	label_counter_cache[label_num] = labelCounter;

	Py_DECREF(labelCounter);
	if (ok < 0) {
	  free(label_counter_cache);
	  Py_XDECREF(labeled_extracted_features_tuple);
	  Py_DECREF(expected_counts);
	  printf ("couldn't set label counter\n");
	  return NULL;
	}
	label_num += 1;
  }

  num_datum = PyTuple_Size(labeled_extracted_features);
  for (datum_index = 0; datum_index < num_datum; datum_index++) {
	PyObject *pair;
	PyObject *datum_label, *datum_features, *feature_probs;

	Py_ssize_t feature_index;
	PyObject *feature, *count;

	pair = PyTuple_GetItem(labeled_extracted_features, datum_index);
	if (PyArg_ParseTuple(pair, "OO", &datum_label, &datum_features) < 0) {
	  printf ("ParseTuple failed\n");
	  Py_XDECREF(labeled_extracted_features_tuple);
	  return NULL;
	}

	feature_probs = PyList_GetItem(log_probs, datum_index);

	if (! feature_probs) {
	  printf("Couldn't get feature_probs\n");

	  free(label_counter_cache);
	  Py_XDECREF(labeled_extracted_features_tuple);
	  Py_DECREF(expected_counts);
	  return NULL;
	}

	feature_index = 0;
	while (PyDict_Next(datum_features, &feature_index, &feature, &count)) {
	  double featureCount = PyFloat_AsDouble(count);

	  label_index = 0;
	  label_num = 0;
	  while (_PySet_Next(labels, &label_index, &label)) {
		PyObject *oldValue, *newValue, *logProb, *labelCounter;
		double oldCount = 0.0;
		int ok;

		labelCounter = label_counter_cache[label_num];
		oldValue = PyDict_GetItem(labelCounter, feature);

		if (oldValue) {
		  oldCount = PyFloat_AsDouble(oldValue);
		}

		logProb = PyDict_GetItem(feature_probs, label);

		if (! logProb) {
		  printf("Couldn't get logProb\n");
		  free(label_counter_cache);
		  Py_DECREF(expected_counts);
		  Py_XDECREF(labeled_extracted_features_tuple);
		  return NULL;
		}

		newValue = PyFloat_FromDouble(oldCount + exp(PyFloat_AsDouble(logProb)) * featureCount);
		ok = PyDict_SetItem(labelCounter, feature, newValue);

		Py_DECREF(newValue);
		if (ok < 0) {
		  printf ("Couldn't set new value\n");
		  free(label_counter_cache);
		  Py_DECREF(expected_counts);
		  Py_XDECREF(labeled_extracted_features_tuple);
		  return NULL;
		}

		label_num += 1;
	  }
	}
  }

  Py_XDECREF(labeled_extracted_features_tuple);
  free(label_counter_cache);
  return expected_counts;
}

PyDoc_STRVAR(module_doc, "Maximum Entropy function implementation");

static PyMethodDef maxent_methods[] = {
  {"get_log_probabilities", maxent_log_probs, METH_VARARGS, "Calculate the log probs for a datum"},
  {"get_expected_counts", maxent_expected_counts, METH_VARARGS, "Calculate the expected counts for a set of datum given weights and labels"},
  {NULL, NULL, 0, NULL} /* Sentinel */
};

PyMODINIT_FUNC
initmaxent(void) 
{
    PyObject* m;

    m = Py_InitModule3("maxent", maxent_methods, module_doc);
	if (m == NULL)
	  return;

	if (import_nlp() < 0)
	  return;
}
