'''
filter_probes.py
Remove the potential probes that align with transcripts,
unless those transcripts contain significant homology to rRNA.
'''
import HTSeq
from collections import defaultdict
import pandas as pd

def create_genomic_interval(start, end, chrom):
    '''
    Given 1-based blast start, end and chromosome, return an HTSeq genomic interval.
    '''
    #set start < end (blast returns start > end if maps to - strand)
    if start > end:
        start2 = end
        end2 = start
        strand = '-'
    else:
        start2 = start
        end2 = end
        strand = '+'

    start2 = start2 - 1
    iv = HTSeq.GenomicInterval(chrom, start2, end2, strand)
    return iv

def create_alnmt(start, end, chrom, name):
    '''
    Given 1-based blast start, end and chromosome, return an HTSeq Alignment object
    '''
    iv = create_genomic_interval(start, end, chrom)
    r = HTSeq.SequenceWithQualities(b"", str(name), b"")
    alnmt = HTSeq.Alignment(r, iv)
    return alnmt

def overlapper(blast_df, regions, discard_minus_strand = True, mode = 'discard'):
    '''
    Given alignments and genomic array, return aligments that do or do not overlap the array
    mode = discard -> discard alignments that overlap the array (use for rRNA)
    If discard_minus_strand = True, then minus strand alignments will be assumed
    unuseful and not returned.
    e.g. if given rRNA regions, discard_minus_strand and mode = 'discard', will
    only return plus strand alignments that don't overlap the rRNA.
    '''
    indices = []
    for row in blast_df.itertuples():
        if (discard_minus_strand == True) and (row.send < row.sstart):
            continue

        alnmt = create_alnmt(row.sstart, row.send, row.sseqid, row.qseqid)

        iset = None
        for iv2, step_set in regions[alnmt.iv].steps():
            if iset is None:
                iset = step_set.copy()
            else:
                iset.intersection_update(step_set)

        #if aligned to at least 1 feature, keep alignment
        blast_df.at[row.Index, 'gene'] = ','.join(iset)

        if len(iset) > 0:
            if mode == 'keep':
                indices.append(row.Index)

        #otherwise, iset = 0, doesn't align to rRNA, so keep that position masked if mode == discard
        else:
            if mode == 'discard':
                indices.append(row.Index)

    filtered_df = blast_df.reindex(indices)
    return filtered_df

def main(arglist):

    probe_csv = snakemake.input['probe_csv']
    kmer_homology_files = snakemake.input['kmer_homology_files']
    target_homology_files = snakemake.input['target_homology_files']
    filtered_probe_csv = snakemake.output['filtered_probe_csv']

    alnmts = []
    for i in range(0, len(kmer_homology_files)):
        target_blast_df = pd.read_csv(target_homology_files[i])
        kmer_blast_df = pd.read_csv(kmer_homology_files[i])
        regions = [create_genomic_interval(x, y, z) for x, y, z in zip(target_blast_df['sstart'], target_blast_df['send'], target_blast_df['sseqid'])]
        rRNA_genes = HTSeq.GenomicArrayOfSets("auto", stranded = True)
        for r in regions:
            #only count if on the same strand as the rRNA:
            if r.strand == '+':
                rRNA_genes[r] += 'rRNA'

        filt_df = overlapper(kmer_blast_df, rRNA_genes, discard_minus_strand = True, mode = 'discard')
        alnmts.append(set(filt_df['qseqid'].tolist()))

    bad_kmers = set.union(*alnmts)
    df = pd.read_csv(probe_csv, index_col = 'unique_id')
    df['passed_homology_screen'] = ~df.index.isin(bad_kmers)
    df[df['passed_homology_screen']].to_csv(filtered_probe_csv)

if __name__ == '__main__':
    main(sys.argv[1:])
