#!/usr/bin/env python
import sys, os, glob

def main(fp1,fp2):
    if (os.path.exists('data/0')):
        print('found old data, removing ...')
        os.system('rm -rf data')
    if (os.path.exists('upload.zip')):
        os.system('rm -f upload.zip')
    os.system('mkdir -p data/0')
    density = 1000
    cmd = 'wirecell-img bee-blobs -g protodunevd-test -s uniform -d %f --speed "-1.473*mm/us" --t0 "250*us" --x0 "-337.3*cm" -o data/0/0-rec.json %s' % (density, fp1, )
    print(cmd)
    os.system(cmd)
    cmd = 'wirecell-img bee-blobs -g protodunevd-test -s uniform -d %f --speed "-1.473*mm/us" --t0 "250*us" --x0 "-337.3*cm" -o data/0/0-bdf.json %s' % (density, fp2, )
    print(cmd)
    os.system(cmd)
    os.system('zip -r upload data')

if __name__ == "__main__":
    if (len(sys.argv)!=3):
        print("usage: python wct-img-2-bee.py 'fp1' 'fp2'")
    else:
        main(sys.argv[1],sys.argv[2])
