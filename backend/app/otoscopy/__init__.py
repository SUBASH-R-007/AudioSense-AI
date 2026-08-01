"""Otoscopy — reading the tympanic membrane, and tying it to the audiogram.

The audiogram says how much hearing is lost and where the lesion sits
functionally. Otoscopy says what the ear actually looks like. Together they
either agree — a flat tympanogram, a conductive gap and a fluid level behind
the drum all telling the same story — or they do not, which is itself the
finding.

Layout:
    taxonomy.py  the eight reference patterns and what each implies clinically
    features.py  illumination-normalised image descriptors (OpenCV only)
    model.py     training, inference, reference retrieval, model provenance
"""
