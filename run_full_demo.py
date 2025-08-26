#!/usr/bin/env python3
"""
Full Demo Script for InnoLab - Complete Scan-Analyze-Fix Workflow
Based on FixChain/run/run_demo.py but adapted for modular InnoLab architecture
"""

import os
import sys
import json
import time
import requests
from datetime import datetime
from typing import List, Dict
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class InnoLabFullDemo:
    """Full demo workflow for InnoLab with scan-analyze-fix cycle"""
    
    def __init__(self, project_name="Flask_App", scanners="bearer", fixers="llm", mode="local", max_iterations=5):
        self.project_name = project_name
        self.scanners = scanners.split(',') if isinstance(scanners, str) else scanners
        self.fixers = fixers.split(',') if isinstance(fixers, str) else fixers
        self.mode = mode
        self.max_iterations = max_iterations
        
        # Service endpoints
        self.scan_service_url = "http://localhost:8001"
        self.autofix_service_url = "http://localhost:8002"
        self.rag_service_url = "http://localhost:8003"
        
        # Project paths
        self.project_path = os.path.join(os.getcwd(), "projects", "demo_apps", project_name)
        self.results_dir = os.path.join(os.getcwd(), "results", datetime.now().strftime("%Y%m%d_%H%M%S"))
        os.makedirs(self.results_dir, exist_ok=True)
        
        print(f"🚀 InnoLab Full Demo Initialized")
        print(f"Project: {self.project_name}")
        print(f"Scanners: {', '.join(self.scanners)}")
        print(f"Fixers: {', '.join(self.fixers)}")
        print(f"Mode: {self.mode}")
        print(f"Max iterations: {self.max_iterations}")
        print(f"Results directory: {self.results_dir}")
        print("-" * 60)
    
    def check_services(self) -> bool:
        """Check if all required services are running"""
        services = {
            "ScanModule": f"{self.scan_service_url}/health",
            "AutoFixModule": f"{self.autofix_service_url}/health"
        }
        
        print("🔍 Checking services...")
        for service_name, health_url in services.items():
            try:
                response = requests.get(health_url, timeout=5)
                if response.status_code == 200:
                    print(f"✅ {service_name} is healthy")
                else:
                    print(f"❌ {service_name} is not healthy (status: {response.status_code})")
                    return False
            except requests.exceptions.RequestException as e:
                print(f"❌ {service_name} is not responding: {e}")
                return False
        
        return True
    
    def scan_project(self, scanner_type: str) -> Dict:
        """Scan project using specified scanner"""
        print(f"🔍 Scanning with {scanner_type}...")
        
        scan_data = {
            "project_path": self.project_path,
            "scanner_type": scanner_type
        }
        
        try:
            response = requests.post(
                f"{self.scan_service_url}/api/v1/scan/single",
                json=scan_data,
                timeout=300  # 5 minutes timeout for scanning
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ Scan completed: {result.get('issues_count', 0)} issues found")
                return result
            else:
                print(f"❌ Scan failed: {response.status_code} - {response.text}")
                return {"status": "error", "message": response.text}
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Scan request failed: {e}")
            return {"status": "error", "message": str(e)}
    
    def analyze_bugs(self, bugs: List[Dict], use_rag: bool = False) -> Dict:
        """Analyze bugs using AutoFixModule"""
        print(f"🧠 Analyzing {len(bugs)} bugs...")
        
        analysis_data = {
            "bugs": bugs,
            "use_rag": use_rag,
            "mode": self.mode
        }
        
        try:
            response = requests.post(
                f"{self.autofix_service_url}/analyze",
                json=analysis_data,
                timeout=120  # 2 minutes timeout for analysis
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ Analysis completed: {result.get('bugs_to_fix', 0)} bugs to fix")
                return result
            else:
                print(f"❌ Analysis failed: {response.status_code} - {response.text}")
                return {"status": "error", "message": response.text}
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Analysis request failed: {e}")
            return {"status": "error", "message": str(e)}
    
    def fix_bugs(self, bugs: List[Dict], use_rag: bool = False) -> Dict:
        """Fix bugs using AutoFixModule"""
        print(f"🔧 Fixing {len(bugs)} bugs...")
        
        fix_data = {
            "bugs": bugs,
            "project_path": self.project_path,
            "use_rag": use_rag,
            "mode": self.mode
        }
        
        try:
            response = requests.post(
                f"{self.autofix_service_url}/fix",
                json=fix_data,
                timeout=300  # 5 minutes timeout for fixing
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ Fix completed: {result.get('fixed_count', 0)} bugs fixed")
                return result
            else:
                print(f"❌ Fix failed: {response.status_code} - {response.text}")
                return {"status": "error", "message": response.text}
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Fix request failed: {e}")
            return {"status": "error", "message": str(e)}
    
    def save_iteration_result(self, iteration: int, result: Dict):
        """Save iteration result to file"""
        filename = f"iteration_{iteration}_{datetime.now().strftime('%H%M%S')}.json"
        filepath = os.path.join(self.results_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        print(f"💾 Iteration {iteration} result saved to: {filename}")
    
    def run_full_workflow(self, use_rag: bool = False) -> Dict:
        """Run the complete scan-analyze-fix workflow"""
        start_time = datetime.now()
        print(f"\n🚀 Starting full workflow {'with' if use_rag else 'without'} RAG")
        print(f"Start time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Check services first
        if not self.check_services():
            return {"status": "error", "message": "Required services are not available"}
        
        iterations = []
        total_bugs_fixed = 0
        
        for iteration in range(1, self.max_iterations + 1):
            print(f"\n=== ITERATION {iteration}/{self.max_iterations} ===")
            
            iteration_result = {
                "iteration": iteration,
                "timestamp": datetime.now().isoformat(),
                "scan_results": [],
                "analysis_result": None,
                "fix_result": None
            }
            
            # Phase 1: Scan with all configured scanners
            all_bugs = []
            for scanner in self.scanners:
                scan_result = self.scan_project(scanner)
                iteration_result["scan_results"].append({
                    "scanner": scanner,
                    "result": scan_result
                })
                
                if scan_result.get("status") == "success":
                    bugs = scan_result.get("vulnerabilities", [])
                    all_bugs.extend(bugs)
            
            bugs_found = len(all_bugs)
            print(f"📊 Total bugs found across all scanners: {bugs_found}")
            
            # Early exit if no bugs found
            if bugs_found == 0:
                print("✅ No bugs found - workflow completed successfully")
                iteration_result["status"] = "completed"
                iteration_result["message"] = "No bugs found"
                iterations.append(iteration_result)
                break
            
            # Phase 2: Analyze bugs
            analysis_result = self.analyze_bugs(all_bugs, use_rag)
            iteration_result["analysis_result"] = analysis_result
            
            if analysis_result.get("status") == "error":
                print(f"❌ Analysis failed: {analysis_result.get('message')}")
                iteration_result["status"] = "failed"
                iterations.append(iteration_result)
                break
            
            # Get real bugs to fix from analysis
            real_bugs = analysis_result.get("list_bugs", [])
            if isinstance(real_bugs, str):
                try:
                    real_bugs = json.loads(real_bugs)
                except json.JSONDecodeError:
                    real_bugs = []
            
            bugs_to_fix = len(real_bugs)
            print(f"🎯 Real bugs to fix after analysis: {bugs_to_fix}")
            
            # Early exit if no real bugs to fix
            if bugs_to_fix == 0:
                print("✅ No real bugs to fix after analysis")
                iteration_result["status"] = "completed"
                iteration_result["message"] = "No real bugs to fix after analysis"
                iterations.append(iteration_result)
                break
            
            # Phase 3: Fix bugs
            fix_result = self.fix_bugs(real_bugs, use_rag)
            iteration_result["fix_result"] = fix_result
            
            if fix_result.get("status") == "error":
                print(f"❌ Fix failed: {fix_result.get('message')}")
                iteration_result["status"] = "failed"
                iterations.append(iteration_result)
                break
            
            # Update counters
            fixed_count = fix_result.get("fixed_count", 0)
            total_bugs_fixed += fixed_count
            iteration_result["bugs_fixed"] = fixed_count
            iteration_result["status"] = "success"
            
            print(f"✅ Iteration {iteration} completed: {fixed_count} bugs fixed")
            
            # Save iteration result
            self.save_iteration_result(iteration, iteration_result)
            iterations.append(iteration_result)
            
            # Brief pause between iterations
            if iteration < self.max_iterations:
                print("⏳ Waiting 5 seconds before next iteration...")
                time.sleep(5)
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        # Prepare final result
        final_result = {
            "project_name": self.project_name,
            "scanners": self.scanners,
            "fixers": self.fixers,
            "mode": self.mode,
            "use_rag": use_rag,
            "total_bugs_fixed": total_bugs_fixed,
            "total_iterations": len(iterations),
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration_seconds": duration,
            "iterations": iterations,
            "results_directory": self.results_dir
        }
        
        # Save final result
        final_result_file = os.path.join(self.results_dir, "final_result.json")
        with open(final_result_file, 'w', encoding='utf-8') as f:
            json.dump(final_result, f, indent=2, ensure_ascii=False)
        
        # Print summary
        print(f"\n🎉 WORKFLOW COMPLETED")
        print(f"Total iterations: {len(iterations)}")
        print(f"Total bugs fixed: {total_bugs_fixed}")
        print(f"Duration: {duration:.2f} seconds")
        print(f"Results saved to: {self.results_dir}")
        
        return final_result

def main():
    """Main function to run the full demo"""
    import argparse
    
    parser = argparse.ArgumentParser(description='InnoLab Full Demo - Complete Scan-Analyze-Fix Workflow')
    parser.add_argument('--project', type=str, default='Flask_App',
                       help='Project name to scan (default: Flask_App)')
    parser.add_argument('--scanners', type=str, default='bearer',
                       help='Comma-separated scanners to use (default: bearer)')
    parser.add_argument('--fixers', type=str, default='llm',
                       help='Comma-separated fixers to use (default: llm)')
    parser.add_argument('--mode', choices=['cloud', 'local'], default='local',
                       help='Dify mode to use (default: local)')
    parser.add_argument('--max_iterations', type=int, default=5,
                       help='Maximum iterations (default: 5)')
    parser.add_argument('--use_rag', action='store_true',
                       help='Use RAG for analysis and fixing')
    
    args = parser.parse_args()
    
    # Create and run demo
    demo = InnoLabFullDemo(
        project_name=args.project,
        scanners=args.scanners,
        fixers=args.fixers,
        mode=args.mode,
        max_iterations=args.max_iterations
    )
    
    result = demo.run_full_workflow(use_rag=args.use_rag)
    
    if result.get("total_bugs_fixed", 0) > 0:
        print(f"\n🎯 SUCCESS: Fixed {result['total_bugs_fixed']} bugs in {result['total_iterations']} iterations")
    else:
        print(f"\n✅ COMPLETED: No bugs needed fixing")

if __name__ == "__main__":
    main()