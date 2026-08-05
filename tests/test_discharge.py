import unittest

from rwd_extraction.discharge import extract_section, parse_discharge_sections


class DischargeParsingTests(unittest.TestCase):
    def test_extracts_sections_and_keeps_past_surgical_history(self):
        text = (
            "Chief Complaint:\nFever and cough\n"
            "History of Present Illness\nTwo days of fever.\n"
            "Past Medical History:\nHypertension\n"
            "Past Surgical History:\nAppendectomy\n"
            "Family History:\nNoncontributory\n"
            "Medications on Admission:\nAspirin\n"
            "Follow Up Instructions:\nSee primary care."
        )
        sections = parse_discharge_sections(text)
        self.assertEqual(sections["chief_complaint"], "Fever and cough")
        self.assertIn("Past Surgical History:\nAppendectomy", sections["past_medical_history"])
        self.assertEqual(sections["discharge_record"], "See primary care.")

    def test_requires_heading_on_its_own_line(self):
        text = "Chief Complaint: fever\nHistory of Present Illness:\nIllness text"
        self.assertIsNone(extract_section(text, ["Chief Complaint"]))

    def test_uses_first_nonempty_repeated_section(self):
        text = "Chief Complaint:\nChief Complaint:\nDyspnea\nPhysical Exam:\nNormal"
        self.assertEqual(extract_section(text, ["Chief Complaint"]), "Dyspnea")

    def test_followup_underscores_are_missing(self):
        sections = parse_discharge_sections("Chief Complaint:\nPain\nFollowup Instructions:\n___")
        self.assertIsNone(sections["discharge_record"])

    def test_explicit_none_is_valid_source_text(self):
        sections = parse_discharge_sections(
            "Chief Complaint:\nPain\nPast Medical History:\nNone\nMedications on Admission:\nNone"
        )
        self.assertEqual(sections["past_medical_history"], "None")
        self.assertEqual(sections["medications_on_admission"], "None")


if __name__ == "__main__":
    unittest.main()
