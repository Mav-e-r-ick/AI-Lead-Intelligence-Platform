"""Abstract interfaces (contracts) the application layer depends on.

SourceReaderPort (below) is implemented today by ExcelSourceReader.
Future ports to be added: EmailVerifierPort, PhoneVerifierPort,
LinkedInDataPort, AIMessageGeneratorPort, EmailSenderPort. Infrastructure
code implements these interfaces, which is what lets a vendor be swapped
out without touching any use case.
"""

from lead_intelligence.application.ports.source_reader_port import SourceReaderPort

__all__ = ["SourceReaderPort"]
