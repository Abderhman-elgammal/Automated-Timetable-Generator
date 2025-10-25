# streamlit_app.py (النسخة المحدثة مع عرض الجداول حسب التخصص)

import streamlit as st
import pandas as pd
import time

from main import load_data, preprocess_and_validate_data, CSPSolver

def format_timetable_display(df):
    """
    دالة لتنسيق الجدول وتحويله إلى شكل عرض مناسب (pivot table).
    """
    if df.empty: return pd.DataFrame()

    df['cell_content'] = "<b>" + df['Course'] + " (" + df['Type'] + ")</b><br>🧑‍🏫 " + df['Instructor'] + "<br>📍 " + df['Room']
    
    timetable_pivot = df.pivot_table(
        index='Time', columns='Day', values='cell_content',
        aggfunc=lambda x: '<br>---<br>'.join(x)
    ).fillna('')

    days_order = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday"]
    ordered_columns = [day for day in days_order if day in timetable_pivot.columns]
    return timetable_pivot[ordered_columns]

def get_specialization_timetables(df, semester):
    """
    تقسيم الجدول إلى جداول حسب التخصص للفصلين 5 و7
    """
    specialization_map = {
        'AID': ['AID 311', 'AID 312', 'AID 321', 'AID 411', 'AID 413', 'AID 417', 'AID 427', 'AID 428'],
        'BIF': ['BIF 311', 'BIF 411', 'BIF 412', 'BIF 413', 'BIF 424', 'BIF 425'],
        'CNC': ['CNC 311', 'CNC 312', 'CNC 314', 'CNC 324', 'CNC 411', 'CNC 413', 'CNC 415', 'CNC 418', 'CNC 419'],
        'CSC': ['CSC 314', 'CSC 315', 'CSC 317', 'CSC 410', 'CSC 411', 'CSC 412', 'CSC 414', 'CSC 415', 'CSC 426']
    }
    
    # للفصل 3 نضيف المواد العامة
    if semester == 3:
        specialization_map['General'] = ['CSC 114', 'CSC 211', 'CSC 317', 'CNC 111', 'CSE 214', 'ACM 215', 'MTH 212', 'LRA 306', 'LRA 403']
    
    # للفصل 1 نضيف المواد العامة
    if semester == 1:
        specialization_map['General'] = ['CSC 111', 'ECE 111', 'MTH 111', 'PHY 113', 'LRA 101', 'LRA 104', 'LRA 105', 'LRA 401']
    
    timetables = {}
    for specialization, courses in specialization_map.items():
        # استخراج المواد التي تبدأ بأي من الكورسات في القائمة
        specialization_courses = []
        for course_pattern in courses:
            course_prefix = course_pattern.split()[0]  # الحصول على الاختصار مثل 'AID'
            specialization_courses.extend([col for col in df['Course Code'].unique() if col.startswith(course_prefix)])
        
        specialization_df = df[df['Course Code'].isin(specialization_courses)]
        timetables[specialization] = specialization_df
    
    return timetables

# ================== واجهة التطبيق الرئيسية ==================

st.set_page_config(layout="wide", page_title="CSP Timetable Generator")
st.title("🎓 Automated Timetable Generator")

# --- الشريط الجانبي للإعدادات ---
st.sidebar.header("⚙️ Settings")
selected_semesters = st.sidebar.multiselect(
    "Select semesters to schedule:",
    options=[1, 3, 5, 7],
    default=[1, 3, 5, 7]
)

if 'solution_df' not in st.session_state:
    st.session_state.solution_df = None

if st.sidebar.button("🚀 Generate Timetable", type="primary"):
    if not selected_semesters:
        st.sidebar.error("Please select at least one semester.")
    else:
        with st.spinner("Analyzing data and constraints..."):
            courses, instructors, rooms, sorted_timeslots, timeslots_dict = load_data()
            variables = [c for c in courses if c.get('semester') in selected_semesters]
            
            st.info(f"Attempting to schedule {len(variables)} sessions for semesters: {', '.join(map(str, selected_semesters))}")
            time.sleep(1)
            
            # --- خطوة التحقق الذكي ---
            domains, diagnostics = preprocess_and_validate_data(variables, instructors, rooms, sorted_timeslots)

        if diagnostics:
            st.error("🚨 Critical data issues found! The solver cannot proceed.")
            st.warning("The following courses are impossible to schedule based on the current data:")
            for var_id, reason in diagnostics.items():
                st.markdown(f"- **{reason}**")
            st.session_state.solution_df = None
        else:
            with st.spinner("Data validation passed! Running the intelligent solver... This might take a moment..."):
                start_time = time.time()
                solver_vars = [v for v in variables if v['id'] in domains]
                solver = CSPSolver(solver_vars, domains)
                solution = solver.solve()
                end_time = time.time()

            if solution:
                st.success(f"✅ Timetable generated successfully in {end_time - start_time:.2f} seconds!")
                df_list = []
                for var_id, assignment in solution.items():
                    info = timeslots_dict[assignment['slots'][0]]
                    df_list.append({
                        'Semester': assignment['course']['semester'],
                        'Course': assignment['course']['name'],
                        'Course Code': assignment['course']['courseId'],  # إضافة كود المادة للتخصص
                        'Type': assignment['course']['type'],
                        'Instructor': assignment['instructor']['name'],
                        'Room': assignment['room']['roomId'],
                        'Day': info['day'],
                        'Time': info['startTime'],
                        'Specialization': assignment['course']['specialization']
                    })
                st.session_state.solution_df = pd.DataFrame(df_list)
            else:
                st.error(f"❌ Could not find a solution that satisfies all constraints. (Attempt took {end_time - start_time:.2f} seconds)")
                st.warning("This usually means the constraints are too tight (e.g., not enough rooms or instructors for the required number of classes at the same time). Try scheduling fewer semesters at once.")
                st.session_state.solution_df = None

# --- عرض النتائج ---
st.markdown("---")
if st.session_state.solution_df is not None:
    df = st.session_state.solution_df
    st.header("🗓️ Generated Timetable")
    
    for semester in sorted(df['Semester'].unique()):
        with st.expander(f"View Timetable for Semester {semester}", expanded=True):
            semester_df = df[df['Semester'] == semester]
            
            # للفصلين 5 و7 نعرض جداول منفصلة لكل تخصص
            if semester in [5, 7]:
                specialization_timetables = get_specialization_timetables(semester_df, semester)
                
                for specialization, spec_df in specialization_timetables.items():
                    if not spec_df.empty:
                        st.subheader(f"📚 {specialization} Specialization - Semester {semester}")
                        pivot_table = format_timetable_display(spec_df)
                        st.markdown(pivot_table.to_html(escape=False), unsafe_allow_html=True)
                        st.markdown("---")
            else:
                # للفصلين 1 و3 نعرض جدول واحد
                pivot_table = format_timetable_display(semester_df)
                st.markdown(pivot_table.to_html(escape=False), unsafe_allow_html=True)
else:
    st.info("Select the semesters you want to schedule in the sidebar and click 'Generate Timetable'.")