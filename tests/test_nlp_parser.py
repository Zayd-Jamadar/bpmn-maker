import unittest

from bpmn_maker.generator.bpmn_builder import BPMNBuilder
from bpmn_maker.generator.layout_engine import LinearLayoutEngine
from bpmn_maker.parser.nlp_parser import NLPParser
from bpmn_maker.reader.base import RawDocument


class NLPParserTest(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = NLPParser()
        self.builder = BPMNBuilder()
        self.layout_engine = LinearLayoutEngine()

    def test_yes_no_gateway_behavior_is_preserved(self) -> None:
        doc = RawDocument(
            paragraphs=[
                "1. Purpose",
                "This procedure outlines the Know Your Customer (KYC) verification steps.",
                "2. Procedure Steps",
                "Receive the new customer application form and supporting identity documents from the front desk.",
                "Enter the customer details into the KYC screening platform (OmniKYC).",
                "Run the automated identity verification check against government ID database.",
                "Review the OmniKYC verification result.",
                "Check if the KYC verification is complete and passed.",
                "If yes, mark the customer record as KYC Approved in the core banking system and proceed to step 8.",
                "If no, generate a KYC deficiency notice and send it to the customer via registered email, requesting the missing documents. Place the application on hold.",
                "Notify the Relationship Manager assigned to the account that KYC review is complete.",
                "File all KYC documents in the customer's digital record in the Document Management System (DMS).",
            ],
            metadata={},
        )

        model = self.parser.parse(doc)
        flow_names = {flow.name for flow in model.flows if flow.name}
        gateway_names = [
            node.name
            for node in model.nodes
            if node.type == "exclusiveGateway" and node.name
        ]

        self.assertIn("Check if the KYC verification is complete and passed.", gateway_names)
        self.assertEqual({"Yes", "No"}, flow_names)

    def test_generic_if_branches_create_nested_gateways(self) -> None:
        doc = RawDocument(
            paragraphs=[
                "1. Purpose",
                "This SOP governs the real-time fraud screening workflow applied to all inbound wire transfers above USD 10,000.",
                "2. Procedure Steps",
                "Receive the inbound wire transfer request from the payment gateway.",
                "Submit the transaction details to the Fraud Detection Engine (FDE) for automated screening.",
                "Retrieve the FDE screening result (Clear, Alert-Low, or Alert-High).",
                "Check if a fraud alert has been raised by the FDE.",
                "If no fraud alert, log the transaction as Cleared and proceed to step 9.",
                "If a fraud alert has been raised, place the transaction in the Fraud Review Queue and assign it to a Fraud Analyst.",
                "The Fraud Analyst must determine the risk level of the alert.",
                "If the risk level is High, escalate the transaction to the Fraud Investigation Unit (FIU) and freeze the associated account pending investigation.",
                "If the risk level is Low, apply enhanced monitoring to the account and proceed with the transaction after adding a manual review note.",
                "Send an automated notification to the customer confirming the transaction status.",
                "Update the transaction status in the core banking system and close the screening record.",
            ],
            metadata={},
        )

        model = self.parser.parse(doc)

        gateway_names = [
            node.name
            for node in model.nodes
            if node.type == "exclusiveGateway" and node.name
        ]
        flow_names = [flow.name for flow in model.flows if flow.name]
        node_names = [node.name for node in model.nodes]

        self.assertEqual(
            [
                "Check if a fraud alert has been raised by the FDE.",
                "The Fraud Analyst must determine the risk level of the alert.",
            ],
            gateway_names,
        )
        self.assertIn("No", flow_names)
        self.assertIn("A fraud alert has been raised", flow_names)
        self.assertIn("The risk level is High", flow_names)
        self.assertIn("The risk level is Low", flow_names)
        self.assertIn(
            "Send an automated notification to the customer confirming the transaction status.",
            node_names,
        )
        update_status = next(
            node
            for node in model.nodes
            if node.name == "Update the transaction status in the core banking system and close the screening record."
        )
        cleared = next(
            node for node in model.nodes if node.name == "log the transaction as Cleared and proceed to step 9."
        )
        self.assertTrue(
            any(
                flow.source_ref == cleared.id and flow.target_ref == update_status.id
                for flow in model.flows
            )
        )

    def test_explicit_step_numbers_take_priority_for_jumps(self) -> None:
        doc = RawDocument(
            paragraphs=[
                "1. Purpose",
                "Test numbered references.",
                "2. Procedure Steps",
                "3. Receive the inbound wire transfer request from the payment gateway.",
                "4. Submit the transaction details to the Fraud Detection Engine (FDE) for automated screening.",
                "5. Retrieve the FDE screening result (Clear, Alert-Low, or Alert-High).",
                "6. Check if a fraud alert has been raised by the FDE.",
                "7. If no fraud alert, log the transaction as Cleared and proceed to step 11.",
                "8. If a fraud alert has been raised, place the transaction in the Fraud Review Queue and assign it to a Fraud Analyst.",
                "9. The Fraud Analyst must determine the risk level of the alert.",
                "10. If the risk level is High, escalate the transaction to the Fraud Investigation Unit (FIU) and freeze the associated account pending investigation.",
                "11. Send an automated notification to the customer confirming the transaction status.",
                "12. Update the transaction status in the core banking system and close the screening record.",
            ],
            metadata={},
        )

        model = self.parser.parse(doc)
        notification = next(
            node
            for node in model.nodes
            if node.name == "Send an automated notification to the customer confirming the transaction status."
        )
        cleared = next(
            node for node in model.nodes if node.name == "log the transaction as Cleared and proceed to step 11."
        )

        self.assertTrue(
            any(
                flow.source_ref == cleared.id and flow.target_ref == notification.id
                for flow in model.flows
            )
        )

    def test_common_branch_target_creates_explicit_converging_gateway(self) -> None:
        doc = RawDocument(
            paragraphs=[
                "1. Purpose",
                "Test reconverging branch output.",
                "2. Procedure Steps",
                "3. Receive the new customer application form and supporting identity documents from the front desk.",
                "4. Review the OmniKYC verification result.",
                "5. Check if the KYC verification is complete and passed.",
                "6. If yes, mark the customer record as KYC Approved in the core banking system and proceed to step 8.",
                "7. If no, generate a KYC deficiency notice and send it to the customer via registered email, requesting the missing documents and proceed to step 8.",
                "8. File all KYC documents in the customer's digital record in the Document Management System (DMS).",
            ],
            metadata={},
        )

        model = self.parser.parse(doc)
        file_task = next(
            node
            for node in model.nodes
            if node.name
            == "File all KYC documents in the customer's digital record in the Document Management System (DMS)."
        )
        merge_gateways = [
            node
            for node in model.nodes
            if node.type == "exclusiveGateway"
            and getattr(node, "gateway_direction", None) == "Converging"
        ]

        self.assertEqual(1, len(merge_gateways))
        merge_gateway = merge_gateways[0]
        self.assertEqual(
            1, sum(1 for flow in model.flows if flow.target_ref == file_task.id)
        )
        self.assertTrue(
            any(
                flow.source_ref == merge_gateway.id and flow.target_ref == file_task.id
                for flow in model.flows
            )
        )

        xml = self.builder.build(model, self.layout_engine.compute(model))
        self.assertIn('gatewayDirection="Converging"', xml)

    def test_branches_that_rejoin_after_intermediate_task_create_merge_gateway(self) -> None:
        doc = RawDocument(
            paragraphs=[
                "1. Purpose",
                "Test delayed reconvergence.",
                "2. Procedure Steps",
                "Receive the new customer application form and supporting identity documents from the front desk.",
                "Enter the customer details into the KYC screening platform (OmniKYC).",
                "Run the automated identity verification check against government ID database.",
                "Review the OmniKYC verification result.",
                "Check if the KYC verification is complete and passed.",
                "If yes, mark the customer record as KYC Approved in the core banking system and proceed to step 9.",
                "If no, generate a KYC deficiency notice and send it to the customer via registered email, requesting the missing documents. Place the application on hold.",
                "Notify the Relationship Manager assigned to the account that KYC review is complete.",
                "File all KYC documents in the customer's digital record in the Document Management System (DMS).",
            ],
            metadata={},
        )

        model = self.parser.parse(doc)
        file_task = next(
            node
            for node in model.nodes
            if node.name
            == "File all KYC documents in the customer's digital record in the Document Management System (DMS)."
        )
        merge_gateways = [
            node
            for node in model.nodes
            if node.type == "exclusiveGateway"
            and getattr(node, "gateway_direction", None) == "Converging"
        ]

        self.assertEqual(1, len(merge_gateways))
        self.assertEqual(
            1, sum(1 for flow in model.flows if flow.target_ref == file_task.id)
        )


if __name__ == "__main__":
    unittest.main()
