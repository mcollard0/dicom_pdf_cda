#!/usr/bin/env python3
"""
dicom_pdf_cda.py

Encapsulate a PDF or CDA (Clinical Document Architecture) document
into a DICOM Part 10 file for storage and retrieval via DICOM 3.0 or DICOMweb.

Supported SOP Classes:
  Encapsulated PDF Storage  1.2.840.10008.5.1.4.1.1.104.1
  Encapsulated CDA Storage  1.2.840.10008.5.1.4.1.1.104.2

Usage:
  python dicom_pdf_cda.py INPUT [options]
  python dicom_pdf_cda.py --help
"""

import argparse;
import datetime;
import os;
import re;
import sys;
from typing import Optional;

try:
    import pydicom;
    from pydicom.dataset import Dataset, FileDataset, FileMetaDataset;
    from pydicom.uid import generate_uid, ExplicitVRLittleEndian;
except ImportError:
    print( "pydicom is required.  Install with:  pip install pydicom" );
    sys.exit( 1 );


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SOP_PDF   = "1.2.840.10008.5.1.4.1.1.104.1";    # Encapsulated PDF Storage
SOP_CDA   = "1.2.840.10008.5.1.4.1.1.104.2";    # Encapsulated CDA Storage
MIME_PDF  = "application/pdf";
MIME_CDA  = "text/xml";

# Fixed UID identifying this tool as the implementation class
IMPL_UID  = "1.2.826.0.1.3680043.9.1055.1";
IMPL_VER  = "dicom_pdf_cda1";  # 16 chars max for SH VR; "pdfcda" portmanteau


# ---------------------------------------------------------------------------
# Type detection
# ---------------------------------------------------------------------------

def detect_type( path: str, data: bytes ) -> Optional[ str ]:
    """
    Return 'pdf', 'cda', or None.

    Detection order:
      1. File extension
      2. PDF magic bytes (%PDF)
      3. CDA XML content sniff (ClinicalDocument namespace/element)
      4. Generic .xml extension defaults to cda
    """
    ext = os.path.splitext( path )[ 1 ].lower();

    if ext == ".pdf":
        return "pdf";

    if ext in ( ".cda", ".cdaxml" ):
        return "cda";

    # PDF magic
    if data[ :4 ] == b"%PDF":
        return "pdf";

    # XML / CDA sniff
    try:
        head = data[ :4096 ].decode( "utf-8", errors="replace" );
        if "ClinicalDocument" in head:
            return "cda";
        if ext == ".xml":
            return "cda";    # generic .xml defaults to CDA
    except Exception:
        pass;

    return None;


# ---------------------------------------------------------------------------
# Value normalisation
# ---------------------------------------------------------------------------

def norm_date( s: str ) -> str:
    """Normalise any common date string to DICOM DA (YYYYMMDD)."""
    s = s.replace( "-", "" ).replace( "/", "" ).strip();
    if len( s ) == 8 and s.isdigit():
        return s;
    raise ValueError( f"Cannot parse date '{s}' -- expected YYYYMMDD or YYYY-MM-DD" );


def norm_time( s: str ) -> str:
    """Normalise any common time string to DICOM TM (HHMMSS)."""
    s = s.replace( ":", "" ).strip();
    if s.isdigit() and 2 <= len( s ) <= 6:
        return s.ljust( 6, "0" );
    raise ValueError( f"Cannot parse time '{s}' -- expected HHMMSS or HH:MM:SS" );


def to_pn( name: str ) -> str:
    """
    Convert a natural 'First [Middle] Last' name to DICOM PN 'Last^First^Middle'.
    If the string already contains '^' it is returned as-is (already DICOM PN format).
    """
    if "^" in name:
        return name;

    parts = name.strip().split();

    if len( parts ) == 1:
        return parts[ 0 ];

    if len( parts ) == 2:
        return f"{ parts[ 1 ] }^{ parts[ 0 ] }";

    # 3+ parts: treat last token as family name, first as given, rest as middle
    return f"{ parts[ -1 ] }^{ parts[ 0 ] }^{ ' '.join( parts[ 1:-1 ] ) }";


# ---------------------------------------------------------------------------
# CDA metadata extraction (best-effort)
# ---------------------------------------------------------------------------

def extract_cda_hints( data: bytes ) -> dict:
    """
    Best-effort extraction of patient/study metadata from CDA XML content.

    Returns a dict with optional keys:
      patient_name, patient_id, study_date, doc_title, hl7_root, hl7_ext
    """
    out = {};

    try:
        text = data.decode( "utf-8", errors="replace" );

        # Patient given / family names
        m = re.search( r"<given[^>]*>(.*?)</given>", text, re.I );
        given  = m.group( 1 ).strip() if m else "";
        m = re.search( r"<family[^>]*>(.*?)</family>", text, re.I );
        family = m.group( 1 ).strip() if m else "";
        if family or given:
            out[ "patient_name" ] = f"{ family }^{ given }" if family else given;

        # Patient ID via US SSN OID (OID 2.16.840.1.113883.4.1)
        for pat in (
            r'<id[^>]+root="2\.16\.840\.1\.113883\.4\.1"[^>]+extension="([^"]+)"',
            r'<id[^>]+extension="([^"]+)"[^>]+root="2\.16\.840\.1\.113883\.4\.1"',
        ):
            m = re.search( pat, text );
            if m:
                out[ "patient_id" ] = m.group( 1 );
                break;

        # Study / effective date
        m = re.search( r"<effectiveTime[^>]+value=\"(\d{8})", text );
        if m:
            out[ "study_date" ] = m.group( 1 );

        # Document title
        m = re.search( r"<title[^>]*>(.*?)</title>", text, re.I | re.DOTALL );
        if m:
            out[ "doc_title" ] = m.group( 1 ).strip();

        # First document-level <id root="..." extension="..."> -- CDA instance ID
        m = re.search( r'<id\s+root="([^"]+)"\s+extension="([^"]+)"', text );
        if m:
            out[ "hl7_root" ] = m.group( 1 );
            out[ "hl7_ext" ]  = m.group( 2 );

    except Exception:
        pass;

    return out;


# ---------------------------------------------------------------------------
# Interactive prompting
# ---------------------------------------------------------------------------

def ask(
    label:    str,
    default:  Optional[ str ] = None,
    required: bool = True,
) -> str:
    """Prompt the user for a value, accepting the default on empty Enter."""
    prompt = (
        f"  {label} [{ default }]: " if default is not None
        else f"  {label}: "
    );
    while True:
        val = input( prompt ).strip();
        if val:
            return val;
        if default is not None:
            return default;
        if not required:
            return "";
        print( "    (required -- please enter a value)" );


def field(
    arg_val:  Optional[ str ],
    label:    str,
    default:  Optional[ str ] = None,
    required: bool = True,
) -> str:
    """Return arg_val if non-empty, otherwise call ask()."""
    if arg_val and arg_val.strip():
        return arg_val.strip();
    return ask( label, default=default, required=required );


# ---------------------------------------------------------------------------
# DICOM dataset assembly
# ---------------------------------------------------------------------------

def build_ds(
    doc_type:     str,
    data:         bytes,
    patient_name: str,
    patient_id:   str,
    study_date:   str,
    study_time:   str,
    accession:    str,
    doc_title:    str,
    institution:  str,
    burned_in:    str,
    charset:      str,
    study_uid:    str,
    series_uid:   str,
    sop_uid:      str,
    hints:        dict,
) -> FileDataset:

    sop_class = SOP_PDF if doc_type == "pdf" else SOP_CDA;
    mime      = MIME_PDF if doc_type == "pdf" else MIME_CDA;
    now       = datetime.datetime.now();

    # File Meta Information (Group 0002)
    file_meta = FileMetaDataset();
    file_meta.MediaStorageSOPClassUID    = sop_class;
    file_meta.MediaStorageSOPInstanceUID = sop_uid;
    file_meta.TransferSyntaxUID          = ExplicitVRLittleEndian;
    file_meta.ImplementationClassUID     = IMPL_UID;
    file_meta.ImplementationVersionName  = IMPL_VER;

    ds = FileDataset( None, {}, file_meta=file_meta, preamble=b"\x00" * 128 );

    # pydicom 2.x compat shim (raises AttributeError in 3.x -- that's fine)
    try:
        ds.is_implicit_VR  = False;
        ds.is_little_endian = True;
    except AttributeError:
        pass;

    # ----------------------------------------------------------------
    # Specific Character Set
    # ISO_IR 192 = UTF-8, which supports all Unicode including CJK, etc.
    # This is particularly important for non-US patient names.
    # ----------------------------------------------------------------
    if charset:
        ds.SpecificCharacterSet = charset;

    # SOP Common Module
    ds.SOPClassUID    = sop_class;
    ds.SOPInstanceUID = sop_uid;

    # Patient Module
    ds.PatientName      = to_pn( patient_name );
    ds.PatientID        = patient_id;
    ds.PatientBirthDate = "";
    ds.PatientSex       = "";

    # General Study Module
    ds.StudyInstanceUID       = study_uid;
    ds.StudyDate              = study_date;
    ds.StudyTime              = study_time;
    ds.AccessionNumber        = accession;
    ds.ReferringPhysicianName = "";
    ds.StudyID                = "1";

    # General Series Module
    ds.SeriesInstanceUID = series_uid;
    ds.SeriesNumber      = "1";
    ds.Modality          = "DOC";

    # General Equipment Module
    ds.Manufacturer = "";
    if institution:
        ds.InstitutionName = institution;

    # SC Equipment Module (required by both Encapsulated PDF and CDA IODs)
    ds.ConversionType = "WSD";    # Workstation

    # Encapsulated Document Module
    ds.ContentDate = now.strftime( "%Y%m%d" );
    ds.ContentTime = now.strftime( "%H%M%S.%f" )[ :13 ];
    ds.BurnedInAnnotation             = burned_in;
    ds.DocumentTitle                  = doc_title;
    ds.MIMETypeOfEncapsulatedDocument = mime;

    # Encapsulated payload -- OB (other bytes) per DICOM standard
    ds.add_new( 0x00420011, "OB", data );

    # CDA-specific: HL7 Instance Identifier (0040,A992) ST
    # Populated from the <id root="..." extension="..."> in the CDA header
    if doc_type == "cda":
        hl7_root = hints.get( "hl7_root", "" );
        hl7_ext  = hints.get( "hl7_ext",  "" );
        if hl7_root:
            hl7_id = f"{ hl7_root }^{ hl7_ext }" if hl7_ext else hl7_root;
            ds.add_new( 0x0040A992, "ST", hl7_id );

    return ds;


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:

    ap = argparse.ArgumentParser(
        description="Encapsulate a PDF or CDA document into a DICOM Part 10 file.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s report.pdf -n "Doe^John^A" --patient-id P1234
  %(prog)s cda_note.xml --study-date 20250301 --accession ACC001
  %(prog)s report.pdf                           (fully interactive)

Character sets (--charset):
  ISO_IR 6     ASCII (US default)
  ISO_IR 100   Latin-1 / Western European
  ISO_IR 192   UTF-8 -- all Unicode incl. CJK  (default for this tool)
  \\ISO 2022 IR 87   Japanese JIS X 0208
        """,
    );

    ap.add_argument( "input",
                     metavar="INPUT_FILE",
                     help="PDF or CDA/XML file to encapsulate" );
    ap.add_argument( "-o", "--output",
                     help="Output .dcm file path (default: replaces input extension with .dcm)" );
    ap.add_argument( "-n", "--name",
                     help="Patient name -- Last^First^Middle  or  'First Last'" );
    ap.add_argument( "--patient-id", dest="patient_id",
                     help="Patient ID" );
    ap.add_argument( "--study-date", dest="study_date",
                     help="Study date  YYYYMMDD  or  YYYY-MM-DD" );
    ap.add_argument( "--study-time", dest="study_time",
                     help="Study time  HHMMSS  or  HH:MM:SS" );
    ap.add_argument( "--accession",
                     help="Accession number (optional)" );
    ap.add_argument( "--title",
                     help="Document title" );
    ap.add_argument( "--institution",
                     help="Institution / facility name (optional)" );
    ap.add_argument( "--study-uid", dest="study_uid",
                     help="Study Instance UID (auto-generated if omitted)" );
    ap.add_argument( "--series-uid", dest="series_uid",
                     help="Series Instance UID (auto-generated if omitted)" );
    ap.add_argument( "--burned-in", dest="burned_in",
                     choices=[ "YES", "NO" ], default="NO",
                     help="BurnedInAnnotation: YES if annotations are baked into the image (default: NO)" );
    ap.add_argument( "--charset", default="ISO_IR 192",
                     help="DICOM SpecificCharacterSet (default: ISO_IR 192 = UTF-8)" );
    ap.add_argument( "--type", dest="force_type",
                     choices=[ "pdf", "cda" ],
                     help="Override auto-detection of document type" );
    ap.add_argument( "-v", "--verbose",
                     action="store_true",
                     help="Print full DICOM dataset after writing" );

    args = ap.parse_args();

    # --- Read input file ---
    if not os.path.isfile( args.input ):
        print( f"Error: file not found: {args.input}" );
        sys.exit( 1 );

    with open( args.input, "rb" ) as fh:
        data = fh.read();

    # --- Detect document type ---
    doc_type = args.force_type or detect_type( args.input, data );

    if doc_type is None:
        print( "Cannot detect document type -- use --type pdf  or  --type cda" );
        sys.exit( 1 );

    print( f"\nDocument type : {doc_type.upper()}  ({len( data ):,} bytes)" );

    # --- Extract CDA hints (best-effort, non-fatal) ---
    hints = {};
    if doc_type == "cda":
        hints = extract_cda_hints( data );
        visible = { k: v for k, v in hints.items() if k not in ( "hl7_root", "hl7_ext" ) };
        if visible:
            print( f"CDA metadata  : { visible }" );

    # --- Gather required fields (prompt for anything not on command line) ---
    now = datetime.datetime.now();
    print( "\nEnter patient / study information  (press Enter to accept [default]):\n" );

    patient_name = field(
        args.name or hints.get( "patient_name" ),
        "Patient name (Last^First or 'First Last')",
    );
    patient_id = field(
        args.patient_id or hints.get( "patient_id" ),
        "Patient ID",
    );
    study_date = norm_date( field(
        args.study_date or hints.get( "study_date" ),
        "Study date",
        default=now.strftime( "%Y%m%d" ),
    ) );
    study_time = norm_time( field(
        args.study_time,
        "Study time",
        default=now.strftime( "%H%M%S" ),
    ) );
    accession = field(
        args.accession,
        "Accession number",
        default="",
        required=False,
    );
    base_name = os.path.splitext( os.path.basename( args.input ) )[ 0 ];
    doc_title = field(
        args.title or hints.get( "doc_title" ),
        "Document title",
        default=base_name,
    );
    institution = field(
        args.institution,
        "Institution",
        default="",
        required=False,
    );

    study_uid  = args.study_uid  or generate_uid();
    series_uid = args.series_uid or generate_uid();
    sop_uid    = generate_uid();

    # --- Build DICOM dataset ---
    ds = build_ds(
        doc_type=doc_type,
        data=data,
        patient_name=patient_name,
        patient_id=patient_id,
        study_date=study_date,
        study_time=study_time,
        accession=accession,
        doc_title=doc_title,
        institution=institution,
        burned_in=args.burned_in,
        charset=args.charset,
        study_uid=study_uid,
        series_uid=series_uid,
        sop_uid=sop_uid,
        hints=hints,
    );

    # --- Determine output path ---
    out_path = args.output or ( os.path.splitext( args.input )[ 0 ] + ".dcm" );

    # --- Write DICOM file ---
    ds.save_as( out_path, write_like_original=False );

    print( f"\nWrote  : {out_path}" );
    print( f"  SOP Class    : {ds.SOPClassUID}" );
    print( f"  Instance UID : {ds.SOPInstanceUID}" );
    print( f"  Patient      : {ds.PatientName} / {ds.PatientID}" );
    print( f"  Study        : {ds.StudyDate}  {ds.StudyTime}" );
    print( f"  Charset      : { getattr( ds, 'SpecificCharacterSet', 'not set' ) }" );
    print( f"  Payload      : {len( data ):,} bytes ({doc_type.upper()})" );

    if args.verbose:
        print( "\n--- DICOM Dataset ---" );
        print( ds );


if __name__ == "__main__":
    main();
