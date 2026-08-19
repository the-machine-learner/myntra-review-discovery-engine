import pandas as pd
import numpy as np

def run_analysis():
    file_path = '../Survey /survey_data.xlsx'
    df = pd.read_excel(file_path)
    
    print("=== SURVEY STATS ===")
    print(f"Total respondents: {df.shape[0]}")
    
    # 1. Main App Used
    print("\n1. MAIN QUICK-COMMERCE APP USED:")
    print(df.iloc[:, 1].value_counts(normalize=True).mul(100).round(1).to_string())
    
    # 2. Demographics (Age & Work/Life Situation)
    print("\n2. WORK / LIFE SITUATION:")
    print(df.iloc[:, 3].value_counts(normalize=True).mul(100).round(1).to_string())
    
    print("\n3. MAINLY SHOP FOR:")
    print(df.iloc[:, 4].value_counts(normalize=True).mul(100).round(1).to_string())
    
    # 4. Conversion rate (bought new category in last 1 month)
    print("\n4. BOUGHT FROM NEW CATEGORIES IN LAST 1 MONTH (YES/NO):")
    print(df.iloc[:, 5].value_counts(normalize=True).mul(100).round(1).to_string())
    
    # 5. Exploring Barriers (Scale 0-5)
    # Mapping question indices to short labels
    barrier_cols = {
        6: "Lack of Trust in other categories",
        7: "Browsing takes too much effort",
        8: "App does not suggest new categories",
        9: "Uses different platforms for other categories",
        10: "Trusted brands are not offered",
        11: "App keeps recommending things already buy (Echo Chamber)",
        12: "Decides elsewhere (Instagram/Friends) first",
        13: "Costly compared to competitors"
    }
    
    print("\n5. RATED BARRIERS TO CROSS-CATEGORY EXPLORATION (Average Score out of 5):")
    barriers = []
    for idx, label in barrier_cols.items():
        col_data = pd.to_numeric(df.iloc[:, idx], errors='coerce').dropna()
        mean_score = col_data.mean()
        high_agreement_pct = (col_data >= 4).sum() / len(col_data) * 100 if len(col_data) > 0 else 0
        barriers.append({
            "Question": label,
            "Mean Score": round(mean_score, 2),
            "Agree Pct (>=4/5)": round(high_agreement_pct, 1)
        })
    barriers_df = pd.DataFrame(barriers).sort_values(by="Mean Score", ascending=False)
    print(barriers_df.to_string(index=False))
    
    # 6. Categories regularly bought
    print("\n6. TOP REGULAR CATEGORIES BOUGHT:")
    all_categories = []
    for val in df.iloc[:, 15].dropna():
        cats = [c.strip() for c in str(val).split(",")]
        all_categories.extend(cats)
    cat_counts = pd.Series(all_categories).value_counts()
    print(cat_counts.to_string())
    
    # 7. Triggers for trying new categories
    print("\n7. TRIGGERS TO COMFORTABLY TRY UNFAMILIAR PRODUCTS:")
    all_triggers = []
    for val in df.iloc[:, 18].dropna():
        trigs = [t.strip() for t in str(val).split(",")]
        all_triggers.extend(trigs)
    trig_counts = pd.Series(all_triggers).value_counts()
    print(trig_counts.to_string())

    # 8. Suggestion timing
    print("\n8. PREFERRED SUGGESTION TIMING:")
    print(df.iloc[:, 19].value_counts(normalize=True).mul(100).round(1).to_string())

if __name__ == "__main__":
    run_analysis()
