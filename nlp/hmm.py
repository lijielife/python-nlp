# Simple HMM implementation. Test code focuses on discrete signal reconstruction.

import sys
import random
from itertools import izip
from collections import defaultdict

from countermap import CounterMap
from nlp import counter as Counter

START_LABEL = "<START>"
STOP_LABEL = "<STOP>"

class HiddenMarkovModel:
	# Distribution over next state given current state
	labels = list()
	transition = CounterMap()
	reverse_transition = CounterMap() # same as transitions but indexed in reverse (useful for decoding)

	# Multinomial distribution over emissions given label
	emission = CounterMap()

	def __pad_sequence(self, sequence, pairs=False):
		if pairs: padding = [(START_LABEL, START_LABEL),]
		else: padding = [START_LABEL,]
		padding.extend(sequence)
		if pairs: padding.append((STOP_LABEL, STOP_LABEL))
		else: padding.append(STOP_LABEL)

		return padding

	def train(self, labeled_sequence):
		label_counts = Counter()
		# Currently this assumes the HMM is multinomial
		last_label = None

		labeled_sequence = self.__pad_sequence(labeled_sequence, pairs=True)

		# Transitions
		for label, emission in labeled_sequence:
			label_counts[label] += 1.0
			self.emission[label][emission] += 1.0
			if last_label:
				self.transition[last_label][label] += 1.0
			last_label = label

		self.transition.normalize()
		self.emission.normalize()
		self.labels = self.emission.keys()

		# Construct reverse transition probabilities
		for label, counter in self.transition.iteritems():
			for sublabel, score in counter.iteritems():
				self.reverse_transition[sublabel][label] = score

	def __get_emission_probs(self, emission):
		# return a Counter distribution over labels given the emission
		emission_prob = Counter()

		for label in self.labels:
			emission_prob[label] = self.emission[label][emission]

		emission_prob.normalize()

		return emission_prob

	def label(self, emission_sequence):
		# This needs to perform viterbi decoding on the the emission sequence
		emission_sequence = self.__pad_sequence(emission_sequence)

		# Backtracking pointers - backtrack[position] = {state : prev, ...}
		backtrack = [dict() for state in emission_sequence]

		# Scores are indexed by pos - 1 in the padded sequence(so we can initialize it with uniform probability, or the stationary if we have it)
		scores = [Counter() for state in emission_sequence]

		# Start is hardcoded
		scores[0][START_LABEL] = 1.0

		for pos, emission in enumerate(emission_sequence[1:]):
#			print "Pos %d (emission %s)" % (pos, emission)
			# At each position calculate the transition scores and the emission probabilities (independent given the state!)
			emission_probs = self.__get_emission_probs(emission)
#			print "  Emission probs:", emission_probs
			scores[pos].normalize()
#			print "  Scores:", scores[pos]

			# scores[pos+1] = max(scores[pos][label] * transitions[label][nextlabel] for label, nextlabel)
			# backtrack = argmax(^^)
			for label in self.labels:
#				print "  label %s" % label
				transition_scores = scores[pos] * self.reverse_transition[label]
#				print "\treverse_transitions:", self.reverse_transition[label]
#				print "\tscores (pre-emission):", transition_scores
				backtrack[pos][label] = transition_scores.arg_max()
#				print "\tbacktrack @ (%s, %d): %s" % (label, pos, backtrack[pos][label])
#				print emission_probs[label], transition_scores * emission_probs[label]
				transition_scores *= emission_probs[label]
#				print "\ttransition scores: ", transition_scores
				scores[pos+1][label] = max(transition_scores.itervalues())
#				print "\tscore @ (%s, %d): %s" % (label, pos, scores[pos+1][label])

		# Now decode
		states = list()
		current = STOP_LABEL
#		print "Kicking off backtracking at %s" % current
		for pos in xrange(len(backtrack)-2, 0, -1):
			current = backtrack[pos][current]
#			print "Backtrack @ %d: %s => %s" % (pos, backtrack[pos], current)
			states.append(current)

#		print "Backtrack finished at %s" % backtrack[1][current]

		states.reverse()
		return states

	def __sample_transition(self, label):
		sample = random.sample()

		for next, prob in self.transition[label].iteritems():
			sample -= prob
			if sample <= 0.0: return next

		assert False, "Should have returned a next state"

	def __sample_emission(self, label):
		sample = random.sample()

		for next, prob in self.emission[label].iteritems():
			sample -= prob
			if sample <= 0.0: return next

		assert False, "Should have returned an emission"

	def sample(self, start=None):
		"""Returns a generator yielding a sequence of (state, emission) pairs
		generated by the modeled sequence"""
		state = start
		if not state:
			state = random.choice(self.transition.keys())
			for i in xrange(1000): state = self.__sample_transition(state)

		while True:
			yield (state, self.__sample_emission(state))
			state = self.__sample_transition(state)

def debug_problem(args):
	# Very simple chain for debugging purposes
	states = ['1', '1', '1', '2', '3', '3', '3', '3']
	emissions = ['y', 'm', 'y', 'm', 'n', 'm', 'n', 'm']

	test_emissions = [['y', 'y', 'y', 'm', 'n', 'm', 'n', 'm'], ['y', 'm', 'n'], ['m', 'n', 'n', 'n']]
	test_labels = [['1', '1', '1', '2', '3', '3', '3', '3'], ['1', '2', '3'], ['2', '3', '3', '3']]

#	test_emissions, test_labels = ([['m', 'n', 'n', 'n']], [['2', '3', '3', '3']])

	chain = HiddenMarkovModel()
	chain.train(zip(states, emissions))

	print "Label"
	for emissions, labels in zip(test_emissions, test_labels):
		print emissions
		guessed_labels = chain.label(emissions)
		print "Guessed: %s" % guessed_labels
		print "Correct: %s" % labels
	print "Transition"
	print chain.transition
	print "Emission"
	print chain.emission

def toy_problem(args):
	# Simulate a 3 state markov chain with transition matrix (given states in row vector):
	#  (destination)
	#   1    2    3
	# 1 0.7  0.3  0
	# 2 0.05 0.4  0.55
	# 3 0.25 0.25 0.5
	transitions = CounterMap()

	transitions['1']['1'] = 0.7
	transitions['1']['2'] = 0.3
	transitions['1']['3'] = 0.0

	transitions['2']['1'] = 0.05
	transitions['2']['2'] = 0.4
	transitions['2']['3'] = 0.55

	transitions['3']['1'] = 0.25
	transitions['3']['2'] = 0.25
	transitions['3']['3'] = 0.5

	def sample_transition(label):
		sample = random.random()

		for next, prob in transitions[label].iteritems():
			sample -= prob
			if sample <= 0.0: return next

		assert False, "Should have returned a next state"

	# And emissions (state, (counter distribution)): {1 : (yes : 0.5, sure : 0.5), 2 : (maybe : 0.75, who_knows : 0.25), 3 : (no : 1)}
	emissions = {'1' : {'yes' : 0.5, 'sure' : 0.5}, '2' : {'maybe' : 0.75, 'who_knows' : 0.25}, '3' : {'no' : 1.0}}

	def sample_emission(label):
		choice = random.random()

		for emission, prob in emissions[label].iteritems():
			choice -= prob
			if choice <= 0.0: return emission

		assert False, "Should have returned an emission"
	
	# Create the training/test data
	states = ['1', '2', '3']
	start = random.choice(states)

	# Burn-in (easier than hand-calculating stationary distribution & sampling)
	for i in xrange(10000):	start = sample_transition(start)

	def label_generator(start_label):
		next = start_label
		while True:
			yield next
			next = sample_transition(next)

	training_labels = [val for _, val in izip(xrange(10000), label_generator(start))]
	training_emissions = [sample_emission(label) for label in training_labels]
	training_signal = zip(training_labels, training_emissions)

	# Training phase
	signal_decoder = HiddenMarkovModel()
	signal_decoder.train(training_signal)

	# Labeling phase: given a set of emissions, guess the correct states
	start = random.choice(states)
	for i in xrange(10000):	start = sample_transition(start)
	test_labels = [val for _, val in izip(xrange(500), label_generator(start))]
	test_emissions = [sample_emission(label) for label in training_labels]

	guessed_labels = signal_decoder.label(test_emissions)
	correct = sum(1 for guessed, correct in izip(guessed_labels, test_labels) if guessed == correct)

	print "%d labels recovered correctly (%.2f%% correct out of %d)" % (correct, 100.0 * float(correct) / float(len(test_labels)), len(test_labels))

if __name__ == "__main__":
	toy_problem(sys.argv)
