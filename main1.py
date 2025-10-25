# main.py (النسخة النهائية المتكاملة - صالحة للاستخدام)

import json
from copy import deepcopy
import time

def load_data():
    """
    تحميل البيانات من ملفات JSON وتجهيز قاموس وقائمة مرتبة للأوقات.
    """
    with open('courses.json', 'r', encoding='utf-8') as f:
        courses = json.load(f)
    with open('instructors.json', 'r', encoding='utf-8') as f:
        instructors = json.load(f)
    with open('rooms.json', 'r', encoding='utf-8') as f:
        rooms = json.load(f)
    with open('timeslots.json', 'r', encoding='utf-8') as f:
        timeslots_list = json.load(f)
    
    timeslots_dict = {slot['id']: slot for slot in timeslots_list}
    
    try:
        sorted_timeslots = sorted(
            timeslots_list,
            key=lambda x: (['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday'].index(x['day']), x['startTime'])
        )
    except (ValueError, KeyError):
        sorted_timeslots = timeslots_list

    return courses, instructors, rooms, sorted_timeslots, timeslots_dict

def preprocess_and_validate_data(variables, instructors, rooms, sorted_timeslots):
    """
    الدالة المحورية: تقوم بإنشاء النطاقات لكل مادة، والأهم، تقوم بالتحقق من صحة البيانات
    وتعيد تقريراً بالأخطاء والمشاكل قبل بدء الحل.
    """
    domains = {}
    diagnostics = {}
    SESSION_SLOTS = 2

    slot_map = {
        sorted_timeslots[i]['id']: sorted_timeslots[i + 1]['id']
        for i in range(len(sorted_timeslots) - 1)
        if sorted_timeslots[i]['day'] == sorted_timeslots[i + 1]['day']
    }

    for var in variables:
        course_id = var['courseId']
        course_type = var['type']
        lab_type = var.get('labType', '')
        specialization = var.get('specialization', 'General')  # الحصول على التخصص
        
        possible_instructors = [
            inst for inst in instructors
            if course_id in inst.get('qualifiedCourses', []) and (
                (course_type in ['Lecture', 'Tut'] and inst.get('role') == 'Prof') or
                (course_type == 'Lab' and inst.get('role') == 'Eng')
            )
        ]

        if not possible_instructors:
            diagnostics[var['id']] = f"Course '{var['name']}' ({course_type}) has NO qualified instructors."
            continue

        possible_rooms = [
            room for room in rooms if
            (course_type in ['Lecture', 'Tut'] and room.get('type') == 'Lecture') or
            (course_type == 'Lab' and (
                (lab_type and room.get('labType') == lab_type) or
                (not lab_type and room.get('type') == 'Lab' and not room.get('labType'))
            ))
        ]

        if not possible_rooms:
            diagnostics[var['id']] = f"Course '{var['name']}' ({course_type}) has NO available rooms of the required type."
            continue
            
        domains[var['id']] = []
        for inst in possible_instructors:
            for room in possible_rooms:
                for start_slot_id, next_slot_id in slot_map.items():
                    assignment = {
                        'instructor': inst, 'room': room,
                        'slots': [start_slot_id, next_slot_id], 'course': var
                    }
                    domains[var['id']].append(assignment)
        
        if not domains.get(var['id']):
             diagnostics[var['id']] = f"Course '{var['name']}' ({course_type}) had qualified instructors and rooms, but 0 possible (room, instructor, time) combinations were found."

    return domains, diagnostics

# ================== كلاس الـ Solver المطور والنهائي ==================
class CSPSolver:
    """
    الـ Solver المطور الذي يستخدم Backtracking, MRV Heuristic, و LCV Heuristic.
    """
    def __init__(self, variables, domains):
        self.variables = variables
        self.domains = domains
        self.assignments = {}

    def solve(self):
        return self.backtrack(self.domains)

    def get_ordered_values(self, var, current_domains):
        """
        ترتيب القيم الممكنة للمتغير باستخدام LCV Heuristic.
        يبدأ بالقيمة التي تترك أكبر عدد من الخيارات للمتغيرات الأخرى.
        """
        unassigned_vars = [v for v in self.variables if v['id'] not in self.assignments and v['id'] != var['id']]
        
        def count_eliminated_choices(value):
            eliminated_count = 0
            for other_var in unassigned_vars:
                for other_value in current_domains.get(other_var['id'], []):
                    time_overlap = any(slot in value['slots'] for slot in other_value['slots'])
                    if time_overlap:
                        if value['instructor']['id'] == other_value['instructor']['id']:
                            eliminated_count += 1
                        elif value['room']['id'] == other_value['room']['id']:
                            eliminated_count += 1
                        elif value['course']['semester'] == other_value['course']['semester']:
                            eliminated_count += 1
            return eliminated_count

        return sorted(current_domains.get(var['id'], []), key=count_eliminated_choices)

    def backtrack(self, current_domains):
        if len(self.assignments) == len(self.variables):
            return self.assignments

        # MRV Heuristic: اختيار المتغير صاحب أقل عدد من القيم المتبقية
        unassigned_vars = [v for v in self.variables if v['id'] not in self.assignments]
        var_to_assign = min(unassigned_vars, key=lambda v: len(current_domains.get(v['id'], [])))

        # LCV Heuristic: الحصول على القيم مرتبة من الأقل تقييداً إلى الأكثر
        ordered_values = self.get_ordered_values(var_to_assign, current_domains)

        for value in ordered_values:
            self.assignments[var_to_assign['id']] = value
            
            pruned_domains = self.forward_check(var_to_assign, value, current_domains)
            
            if pruned_domains is not None:
                result = self.backtrack(pruned_domains)
                if result is not None:
                    return result

            # Backtrack
            del self.assignments[var_to_assign['id']]

        return None

    def forward_check(self, current_var, assigned_value, domains):
        pruned_domains = deepcopy(domains)
        assigned_slots = assigned_value['slots']
        assigned_instructor_id = assigned_value['instructor']['id']
        assigned_room_id = assigned_value['room']['id']
        assigned_semester = assigned_value['course']['semester']

        for var_id, domain_values in list(pruned_domains.items()):
            if var_id == current_var['id'] or var_id in self.assignments:
                continue

            new_domain = []
            for p_asgn in domain_values:
                conflicts = False
                time_overlap = any(slot in assigned_slots for slot in p_asgn['slots'])
                if time_overlap:
                    if p_asgn['instructor']['id'] == assigned_instructor_id: conflicts = True
                    elif p_asgn['room']['id'] == assigned_room_id: conflicts = True
                    elif p_asgn['course']['semester'] == assigned_semester: conflicts = True
                if not conflicts:
                    new_domain.append(p_asgn)
            
            if not new_domain: return None
            pruned_domains[var_id] = new_domain
        return pruned_domains