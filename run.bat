@echo off
cd /d E:\projects\us-market-summary

if not exist logs mkdir logs

python market_summary.py >> logs\market_summary.log 2>&1
