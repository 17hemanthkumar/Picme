import face_recognition
import numpy as np
import os
import pickle

class FaceRecognitionModel:
    def __init__(self, data_file='known_faces.dat'):
        """
        Model storing encodings for multiple known identities.
        Each identity contains multiple encoding samples.
        """
        self.data_file = data_file
        self.known_encodings = []  # List of lists
        self.known_ids = []        # ID labels

        self.load_model()

    def load_model(self):
        """Load existing data file if available."""
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, "rb") as f:
                    self.known_encodings, self.known_ids = pickle.load(f)
                print(f"--- [ML MODEL] Loaded {len(self.known_ids)} identities. ---")
            except Exception as e:
                print(f"--- [ML MODEL] Error loading model: {e}. Starting new model. ---")

    def save_model(self):
        """Save current model."""
        with open(self.data_file, "wb") as f:
            pickle.dump((self.known_encodings, self.known_ids), f)
        print(f"--- [ML MODEL] Model saved with {len(self.known_ids)} identities. ---")

    # ----------------------------------------------------------------------
    # Reinforce existing identity
    # ----------------------------------------------------------------------
    def update_person_encoding(self, index, new_encoding):
        """Append new encodings, keep last 15 samples only."""
        self.known_encodings[index].append(new_encoding)

        # Keep model size small but accurate
        if len(self.known_encodings[index]) > 15:
            self.known_encodings[index] = self.known_encodings[index][-15:]

        self.save_model()

    # ----------------------------------------------------------------------
    # Learning new identity OR matching existing identity
    # ----------------------------------------------------------------------
    def learn_face(self, new_encoding):
        """Learn a new encoding or reinforce an existing identity."""
        if not self.known_encodings:
            new_id = f"person_{len(self.known_ids) + 1:04d}"
            self.known_encodings.append([new_encoding])
            self.known_ids.append(new_id)
            print(f"--- [ML MODEL] First face learned → {new_id} ---")
            return new_id

        # Compute average encodings per user
        avg_encodings = [np.mean(enc_list, axis=0) for enc_list in self.known_encodings]
        distances = face_recognition.face_distance(avg_encodings, new_encoding)

        best_match_index = np.argmin(distances)
        best_distance = distances[best_match_index]

        # Dynamic tolerance
        STRICT_TOLERANCE = 0.55
        RELAXED_TOLERANCE = 0.60  # expanded for group + low light

        if best_distance <= STRICT_TOLERANCE:
            self.update_person_encoding(best_match_index, new_encoding)
            print(f"--- [ML MODEL] Strong match → {self.known_ids[best_match_index]} ({best_distance:.2f}) ---")
            return self.known_ids[best_match_index]


        # If no match found → new identity
        new_id = f"person_{len(self.known_ids) + 1:04d}"
        self.known_encodings.append([new_encoding])
        self.known_ids.append(new_id)
        print(f"--- [ML MODEL] New identity created {new_id} | Dist={best_distance:.2f} ---")
        return new_id

    # ----------------------------------------------------------------------
    # Recognize face
    # ----------------------------------------------------------------------
    def recognize_face(self, encoding):
        """Return matched identity if confidence is high enough."""
        if not self.known_encodings:
            print("--- [ML MODEL] No faces in database ---")
            return None

        avg_encodings = [np.mean(enc_list, axis=0) for enc_list in self.known_encodings]
        distances = face_recognition.face_distance(avg_encodings, encoding)

        best_match_index = np.argmin(distances)
        best_distance = distances[best_match_index]

        STRICT_TOLERANCE = 0.55
        RELAXED_TOLERANCE = 0.60

        if best_distance <= STRICT_TOLERANCE:
            print(f"--- [ML MODEL] STRONG MATCH {self.known_ids[best_match_index]} ({best_distance:.2f}) ---")
            return self.known_ids[best_match_index]

        print(f"--- [ML MODEL] No Match Found (best={best_distance:.2f}) ---")
        return None
