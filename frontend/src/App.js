import React, { useState, useEffect, useMemo } from 'react';
import './App.css';
import CourseSearchForm from './CourseSearchForm';
import CourseList from './CourseList';
import { searchCourses, updateDatabase, getCourseDetails } from './api';

import { Calendar, momentLocalizer } from 'react-big-calendar';
import moment from 'moment';
import 'react-big-calendar/lib/css/react-big-calendar.css';

const localizer = momentLocalizer(moment);

// Helper function to parse 'meets' string into calendar events
const parseMeetsString = (course) => {
    const events = [];
    const daysMap = {
        'M': 1, // Monday
        'T': 2, // Tuesday
        'W': 3, // Wednesday
        'R': 4, // Thursday
        'F': 5, // Friday
        'S': 6, // Saturday
        'U': 0  // Sunday
    };

    if (!course.meets || course.meets.trim() === '') {
        console.warn('No meets data for course:', course.course_code);
        return events;
    }

    console.log('Meets string:', course.meets);

    // Use course-specific dates, fallback to defaults if not available
    const startDate = course.start_date || course.courseDetails?.meet_start_date;
    const endDate = course.end_date || course.courseDetails?.meet_end_date;
    
    console.log('Course dates:', { course_code: course.course_code, startDate, endDate });
    
    if (!startDate || !endDate) {
        console.warn('No dates available for course:', course.course_code);
        return events; // Can't create events without dates
    }

    // Parse dates - handle multiple formats: "YYYY-MM-DD", "1/20/2026", or "1/20"
    let SEMESTER_START_DATE, SEMESTER_END_DATE;
    
    try {
        // Check if dates are in ISO format (YYYY-MM-DD)
        if (startDate.includes('-')) {
            SEMESTER_START_DATE = moment(startDate, 'YYYY-MM-DD');
            SEMESTER_END_DATE = moment(endDate, 'YYYY-MM-DD');
        } else if (startDate.includes('/')) {
            // Handle M/D/YYYY or M/D format
            const startParts = startDate.split('/');
            const endParts = endDate.split('/');
            
            const startYear = startParts.length === 3 ? startParts[2] : '2026';
            const endYear = endParts.length === 3 ? endParts[2] : '2026';
            
            SEMESTER_START_DATE = moment(`${startParts[0]}/${startParts[1]}/${startYear}`, 'M/D/YYYY');
            SEMESTER_END_DATE = moment(`${endParts[0]}/${endParts[1]}/${endYear}`, 'M/D/YYYY');
        } else {
            console.error('Unknown date format:', startDate, endDate);
            return events;
        }
        
        console.log('Parsed dates:', { 
            start: SEMESTER_START_DATE.format('YYYY-MM-DD'), 
            end: SEMESTER_END_DATE.format('YYYY-MM-DD') 
        });
    } catch (error) {
        console.error('Date parsing error:', error);
        return events; // Can't create events if dates fail to parse
    }

    // Example meets string: "TR 12:30-1:45p" or "M 9:30-10:45a, W 9:30-10:45a"
    const parts = course.meets.split(',').map(part => part.trim());

    console.log('Parsed meets parts:', parts);

    parts.forEach(part => {
        const dayMatch = part.match(/^([MTWRFSU]+)\s(.+)$/);
        if (!dayMatch) {
            console.warn('No day match for:', part);
            return;
        }

        const days = dayMatch[1];
        const timeRange = dayMatch[2];

        console.log('Days:', days, 'Time range:', timeRange);

        // Match times with optional minutes for start time: "8-9:15a" or "8:00-9:15a"
        const timeMatch = timeRange.match(/(\d{1,2})(?::(\d{2}))?([ap])?-(\d{1,2}):(\d{2})([ap])?/);
        if (!timeMatch) {
            console.warn('No time match for:', timeRange);
            return;
        }

        let [, startHourStr, startMinute, startAmPm, endHourStr, endMinute, endAmPm] = timeMatch;

        // Default to :00 if minutes not provided for start time
        if (!startMinute) startMinute = '00';

        let startHour = parseInt(startHourStr);
        // If no am/pm specified for start time, inherit from end time
        if (!startAmPm) startAmPm = endAmPm;
        if (startAmPm === 'p' && startHour !== 12) startHour += 12;
        if (startAmPm === 'a' && startHour === 12) startHour = 0; // Midnight

        let endHour = parseInt(endHourStr);
        if (endAmPm === 'p' && endHour !== 12) endHour += 12;
        if (endAmPm === 'a' && endHour === 12) endHour = 0; // Midnight


        // Iterate through each day in the days string (e.g., "TR")
        days.split('').forEach(dayChar => {
            const dayOfWeek = daysMap[dayChar];
            if (dayOfWeek === undefined) {
                console.warn('Unknown day character:', dayChar);
                return;
            }

            console.log(`Processing ${dayChar} (${dayOfWeek}) from ${SEMESTER_START_DATE.format('YYYY-MM-DD')} to ${SEMESTER_END_DATE.format('YYYY-MM-DD')}`);

            let currentDay = SEMESTER_START_DATE.clone();
            let eventCount = 0;
            while (currentDay.isSameOrBefore(SEMESTER_END_DATE, 'day')) {
                if (currentDay.day() === dayOfWeek) {
                    const start = currentDay.clone().hour(startHour).minute(parseInt(startMinute)).toDate();
                    const end = currentDay.clone().hour(endHour).minute(parseInt(endMinute)).toDate();

                    const title = `${course.course_code} - ${course.title || course.course_title || 'Course'}`;
                    
                    events.push({
                        title: title,
                        start,
                        end,
                        allDay: false,
                        resource: course // Attach the full course object if needed
                    });
                    eventCount++;
                }
                currentDay.add(1, 'day');
            }
            console.log(`Created ${eventCount} events for ${dayChar}`);
        });
    });
    
    console.log(`Generated ${events.length} events for ${course.course_code}`);
    return events;
};


function App() {
    const [isMobile, setIsMobile] = useState(() => {
        if (typeof window === 'undefined') return false;
        return window.innerWidth <= 768;
    });
    const [courses, setCourses] = useState([]);
    const [stagedCourses, setStagedCourses] = useState(() => {
        // Load staged courses from localStorage on initial mount
        try {
            const saved = localStorage.getItem('stagedCourses');
            return saved ? JSON.parse(saved) : [];
        } catch (error) {
            console.error('Failed to load staged courses from localStorage:', error);
            return [];
        }
    });
    const [selectedCourse, setSelectedCourse] = useState(null);
    const [courseDetails, setCourseDetails] = useState(null);
    const [courseDetailsCache, setCourseDetailsCache] = useState(() => {
        // Load course details cache from localStorage on initial mount
        try {
            const saved = localStorage.getItem('courseDetailsCache');
            return saved ? JSON.parse(saved) : {};
        } catch (error) {
            console.error('Failed to load course details cache from localStorage:', error);
            return {};
        }
    });
    const [loadingDetails, setLoadingDetails] = useState(false);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [showCalendar, setShowCalendar] = useState(false);
    const [updating, setUpdating] = useState(false);
    const [updateMessage, setUpdateMessage] = useState(null);
    const [currentView, setCurrentView] = useState(isMobile ? 'day' : 'week');
    const [currentDate, setCurrentDate] = useState(new Date());

    useEffect(() => {
        const mediaQuery = window.matchMedia('(max-width: 768px)');
        const handleViewportChange = (event) => {
            setIsMobile(event.matches);
        };

        setIsMobile(mediaQuery.matches);
        mediaQuery.addEventListener('change', handleViewportChange);

        return () => {
            mediaQuery.removeEventListener('change', handleViewportChange);
        };
    }, []);

    useEffect(() => {
        setCurrentView(isMobile ? 'day' : 'week');
    }, [isMobile]);

    // Save staged courses to localStorage whenever they change
    useEffect(() => {
        try {
            localStorage.setItem('stagedCourses', JSON.stringify(stagedCourses));
        } catch (error) {
            console.error('Failed to save staged courses to localStorage:', error);
        }
    }, [stagedCourses]);

    // Save course details cache to localStorage whenever it changes
    useEffect(() => {
        try {
            localStorage.setItem('courseDetailsCache', JSON.stringify(courseDetailsCache));
        } catch (error) {
            console.error('Failed to save course details cache to localStorage:', error);
        }
    }, [courseDetailsCache]);

    const handleSearch = async (filters) => {
        setLoading(true);
        setError(null);
        try {
            const data = await searchCourses(filters);
            setCourses(data);
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    const handleStageCourse = (course) => {
        setStagedCourses((prevStagedCourses) => {
            if (!prevStagedCourses.some(c => c.section_id === course.section_id)) {
                // Add course with its courseDetails
                const stagedCourse = {
                    ...course,
                    courseDetails: courseDetails // Include the fetched details
                };
                return [...prevStagedCourses, stagedCourse];
            }
            return prevStagedCourses;
        });
        setSelectedCourse(null); // Close the detail panel
        setCourseDetails(null);
    };

    const handleRemoveStagedCourse = (courseId) => {
        setStagedCourses((prevStagedCourses) =>
            prevStagedCourses.filter(course => course.section_id !== courseId)
        );
    };

    const handleCloseDetail = () => {
        setSelectedCourse(null);
        setCourseDetails(null);
    };

    const handleUpdateDatabase = async () => {
        setUpdating(true);
        setUpdateMessage(null);
        try {
            const result = await updateDatabase();
            if (result.status === 'skipped') {
                setUpdateMessage(`ℹ ${result.message}`);
            } else {
                setUpdateMessage(`✓ Database updated successfully! Processed ${result.records_processed} records.`);
            }
            setTimeout(() => setUpdateMessage(null), 5000);
        } catch (err) {
            setUpdateMessage(`✗ Update failed: ${err.message}`);
            setTimeout(() => setUpdateMessage(null), 5000);
        } finally {
            setUpdating(false);
        }
    };

    const handleClearSchedule = () => {
        if (stagedCourses.length === 0) return;
        
        if (window.confirm(`Clear all ${stagedCourses.length} staged courses from your schedule?`)) {
            setStagedCourses([]);
            setSelectedCourse(null);
            setCourseDetails(null);
        }
    };

    const handleSelectCourse = async (course) => {
        setSelectedCourse(course);
        
        // Check if we have cached details for this course code
        const cachedDetails = courseDetailsCache[course.course_code];
        
        if (cachedDetails && cachedDetails.component === course.schd) {
            // Reuse cached details with section-specific meeting info from sections table
            setCourseDetails({
                ...cachedDetails,
                meet_pattern: course.meets,
                meet_start_date: course.start_date,
                meet_end_date: course.end_date
            });
            setLoadingDetails(false);
        } else {
            // No cache or different component, fetch full details
            setCourseDetails(null);
            setLoadingDetails(true);
            
            try {
                const group = `code:${course.course_code}`;
                const key = `crn:${course.crn}`;
                const srcdb = course.srcdb || "1264";
                const matched = `crn:${course.crn}`;
                
                const details = await getCourseDetails(group, key, srcdb, matched);
                
                // Override API meeting data with section table data
                const detailsWithSectionMeeting = {
                    ...details,
                    meet_pattern: course.meets,
                    meet_start_date: course.start_date,
                    meet_end_date: course.end_date
                };
                
                setCourseDetails(detailsWithSectionMeeting);
                
                // Cache the details by course code
                setCourseDetailsCache(prev => ({
                    ...prev,
                    [course.course_code]: detailsWithSectionMeeting
                }));
            } catch (err) {
                console.error('Failed to fetch course details:', err);
            } finally {
                setLoadingDetails(false);
            }
        }
    };

    const calendarEvents = useMemo(() => {
        console.log('Generating calendar events for', stagedCourses.length, 'courses');
        const events = stagedCourses.flatMap(course => parseMeetsString(course));
        console.log('Generated', events.length, 'total events');
        
        // Detect time conflicts
        events.forEach((event, index) => {
            event.hasConflict = false;
            for (let i = 0; i < events.length; i++) {
                if (i === index) continue;
                const other = events[i];
                
                // Check if events overlap
                if (event.start < other.end && event.end > other.start) {
                    event.hasConflict = true;
                    break;
                }
            }
        });
        
        console.log('Events with conflicts:', events.filter(e => e.hasConflict).length);
        return events;
    }, [stagedCourses]);

    const eventStyleGetter = (event) => {
        if (event.hasConflict) {
            return {
                style: {
                    backgroundColor: '#dc3545',
                    borderColor: '#dc3545',
                    color: 'white'
                }
            };
        }
        return {
            style: {
                backgroundColor: '#57068c',
                borderColor: '#57068c',
                color: 'white'
            }
        };
    };

    const handleDownloadICS = () => {
        if (calendarEvents.length === 0) {
            alert('No courses to export. Please add courses to your schedule first.');
            return;
        }

        // Generate ICS file content
        const formatICSDate = (date) => {
            const d = new Date(date);
            return d.toISOString().replace(/[-:]/g, '').split('.')[0] + 'Z';
        };

        let icsContent = [
            'BEGIN:VCALENDAR',
            'VERSION:2.0',
            'PRODID:-//NYU Course Scheduler//EN',
            'CALSCALE:GREGORIAN',
            'METHOD:PUBLISH',
            'X-WR-CALNAME:NYU Course Schedule',
            'X-WR-TIMEZONE:America/New_York'
        ];

        calendarEvents.forEach((event, index) => {
            const uid = `${formatICSDate(event.start)}-${index}@nyu-course-scheduler`;
            icsContent.push(
                'BEGIN:VEVENT',
                `UID:${uid}`,
                `DTSTAMP:${formatICSDate(new Date())}`,
                `DTSTART:${formatICSDate(event.start)}`,
                `DTEND:${formatICSDate(event.end)}`,
                `SUMMARY:${event.title}`,
                'STATUS:CONFIRMED',
                'END:VEVENT'
            );
        });

        icsContent.push('END:VCALENDAR');

        // Create and download file
        const blob = new Blob([icsContent.join('\r\n')], { type: 'text/calendar;charset=utf-8' });
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = 'nyu-course-schedule.ics';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.URL.revokeObjectURL(url);
    };


    return (
        <div className="App">
            <header className="App-header">
                <div className="header-title">
                    <h1>NYU Course Search</h1>
                    <span className="disclaimer-badge">
                        Unofficial. Please double check with Albert.
                    </span>
                </div>
                <div className="header-buttons">
                    <button 
                        className="update-db-btn" 
                        onClick={handleUpdateDatabase}
                        disabled={updating}
                    >
                        {updating ? 'Updating...' : '↻ Update Database'}
                    </button>
                    <button 
                        className="clear-schedule-btn" 
                        onClick={handleClearSchedule}
                        disabled={stagedCourses.length === 0}
                    >
                        🗑️ Clear Schedule
                    </button>
                    <button 
                        className="toggle-calendar-btn" 
                        onClick={() => setShowCalendar(!showCalendar)}
                    >
                        {showCalendar ? 'Hide' : 'Show'} Calendar ({stagedCourses.length})
                    </button>
                </div>
            </header>
            {updateMessage && (
                <div className={`update-message ${updateMessage.startsWith('✓') ? 'success' : updateMessage.startsWith('ℹ') ? 'info' : 'error'}`}>
                    {updateMessage}
                </div>
            )}
            <main className="three-column-layout">
                <aside className="left-sidebar">
                    <section className="search-section">
                        <h2>Search for Classes</h2>
                        <CourseSearchForm onSearch={handleSearch} />
                        {loading && <p className="status-message">Loading courses...</p>}
                        {error && <p className="error-message">Error: {error}</p>}
                        <div className="search-footer">
                            <span>Made by CAS'28</span>
                            <a
                                href="https://github.com/chengus/nyu-bobcat-search"
                                target="_blank"
                                rel="noreferrer"
                            >
                                GitHub
                            </a>
                        </div>
                    </section>
                </aside>

                <div className="main-content">
                    <section className="results-section">
                        <h2>Search Results</h2>
                        <CourseList 
                            courses={courses} 
                            onStageCourse={handleStageCourse} 
                            onSelectCourse={handleSelectCourse}
                            selectedCourse={selectedCourse}
                        />
                    </section>
                </div>

                <aside className="right-sidebar">
                    {selectedCourse ? (
                        <section className="course-detail-section">
                            <div className="detail-header">
                                <h2>{selectedCourse.course_code}</h2>
                                <button className="close-detail-btn" onClick={handleCloseDetail}>✕</button>
                            </div>
                            <h3>{selectedCourse.title || selectedCourse.course_title} ({selectedCourse.no})</h3>
                            
                            {loadingDetails && (
                                <p className="status-message">Loading details...</p>
                            )}
                            
                            {courseDetails && courseDetails.description && (
                                <div className="detail-section">
                                    <h4>Description</h4>
                                    <p className="course-description" dangerouslySetInnerHTML={{ __html: courseDetails.description }}></p>
                                </div>
                            )}
                            
                            {courseDetails && courseDetails.clssnotes && (
                                <div className="detail-section">
                                    <h4>Class Notes</h4>
                                    <p className="course-notes" dangerouslySetInnerHTML={{ __html: courseDetails.clssnotes }}></p>
                                </div>
                            )}
                            
                            {courseDetails && courseDetails.registration_restrictions && (
                                <div className="detail-section">
                                    <h4>Registration Restrictions</h4>
                                    <p className="course-notes" dangerouslySetInnerHTML={{ __html: courseDetails.registration_restrictions }}></p>
                                </div>
                            )}
                            
                            {courseDetails && (courseDetails.hours_html || courseDetails.component || courseDetails.instructional_method || courseDetails.campus_location) && (
                                <div className="detail-group">
                                    {courseDetails.hours_html && (
                                        <div className="detail-item">
                                            <strong>Hours:</strong> <span dangerouslySetInnerHTML={{ __html: courseDetails.hours_html }}></span>
                                        </div>
                                    )}
                                    {courseDetails.component && (
                                        <div className="detail-item">
                                            <strong>Component:</strong> {courseDetails.component}
                                        </div>
                                    )}
                                    {courseDetails.instructional_method && (
                                        <div className="detail-item">
                                            <strong>Method:</strong> {courseDetails.instructional_method}
                                        </div>
                                    )}
                                    {courseDetails.campus_location && (
                                        <div className="detail-item">
                                            <strong>Campus:</strong> {courseDetails.campus_location}
                                        </div>
                                    )}
                                </div>
                            )}
                            
                            {courseDetails && (courseDetails.meet_pattern || courseDetails.meet_start_date || courseDetails.meet_end_date) && (
                                <div className="detail-section">
                                    <h4>Meeting Schedule</h4>
                                    {courseDetails.meet_pattern && (
                                        <div className="detail-item">
                                            <strong>Time:</strong> {courseDetails.meet_pattern}
                                        </div>
                                    )}
                                    {(courseDetails.meet_start_date || courseDetails.meet_end_date) && (
                                        <div className="detail-item">
                                            <strong>Dates:</strong> {courseDetails.meet_start_date} to {courseDetails.meet_end_date}
                                        </div>
                                    )}
                                </div>
                            )}

                            <button 
                                className="add-to-schedule-btn"
                                onClick={() => handleStageCourse(selectedCourse)}
                            >
                                Add to My Schedule
                            </button>
                        </section>
                    ) : (
                        <section className="staged-courses-section">
                            <h2>My Schedule ({stagedCourses.length})</h2>
                            {stagedCourses.length === 0 ? (
                                <p className="empty-state">No courses staged yet. Search and add courses to build your schedule.</p>
                            ) : (
                                <div className="staged-courses-list">
                                    {stagedCourses.map(course => (
                                        <div key={course.section_id} className="course-detail-section">
                                            <div className="detail-header">
                                                <h2>{course.course_code}</h2>
                                                <button 
                                                    className="close-detail-btn"
                                                    onClick={() => handleRemoveStagedCourse(course.section_id)}
                                                    title="Remove from schedule"
                                                >
                                                    ✕
                                                </button>
                                            </div>
                                            <h3>{course.title || course.course_title} ({course.no})</h3>
                                            
                                            {course.courseDetails && course.courseDetails.registration_restrictions && (
                                                <div className="detail-section">
                                                    <h4>Registration Restrictions</h4>
                                                    <p className="course-notes" dangerouslySetInnerHTML={{ __html: course.courseDetails.registration_restrictions }}></p>
                                                </div>
                                            )}
                                            
                                            {course.courseDetails && (course.courseDetails.hours_html || course.courseDetails.component || course.courseDetails.instructional_method || course.courseDetails.campus_location) && (
                                                <div className="detail-group">
                                                    {course.courseDetails.hours_html && (
                                                        <div className="detail-item">
                                                            <strong>Hours:</strong> <span dangerouslySetInnerHTML={{ __html: course.courseDetails.hours_html }}></span>
                                                        </div>
                                                    )}
                                                    {course.courseDetails.component && (
                                                        <div className="detail-item">
                                                            <strong>Component:</strong> {course.courseDetails.component}
                                                        </div>
                                                    )}
                                                    {course.courseDetails.instructional_method && (
                                                        <div className="detail-item">
                                                            <strong>Method:</strong> {course.courseDetails.instructional_method}
                                                        </div>
                                                    )}
                                                    {course.courseDetails.campus_location && (
                                                        <div className="detail-item">
                                                            <strong>Campus:</strong> {course.courseDetails.campus_location}
                                                        </div>
                                                    )}
                                                </div>
                                            )}
                                            
                                            {course.courseDetails && (course.courseDetails.meet_pattern || course.courseDetails.meet_start_date || course.courseDetails.meet_end_date) && (
                                                <div className="detail-section">
                                                    <h4>Meeting Schedule</h4>
                                                    {course.courseDetails.meet_pattern && (
                                                        <div className="detail-item">
                                                            <strong>Time:</strong> {course.courseDetails.meet_pattern}
                                                        </div>
                                                    )}
                                                    {(course.courseDetails.meet_start_date || course.courseDetails.meet_end_date) && (
                                                        <div className="detail-item">
                                                            <strong>Dates:</strong> {course.courseDetails.meet_start_date} to {course.courseDetails.meet_end_date}
                                                        </div>
                                                    )}
                                                </div>
                                            )}
                                        </div>
                                    ))}
                                </div>
                            )}
                        </section>
                    )}
                </aside>
            </main>

            {/* Floating Calendar Modal */}
            {showCalendar && (
                <div className="calendar-modal-wrapper">
                    <div className="calendar-modal-overlay" onClick={() => setShowCalendar(false)} />
                    <div className="calendar-modal">
                        <div className="calendar-modal-header">
                            <h2>My Schedule Calendar</h2>
                            <div className="calendar-header-buttons">
                                <button 
                                    className="download-ics-btn"
                                    onClick={handleDownloadICS}
                                    title="Download schedule as ICS file"
                                >
                                    📅 Download ICS
                                </button>
                                <button 
                                    className="close-calendar-btn" 
                                    onClick={(e) => {
                                        e.stopPropagation();
                                        setShowCalendar(false);
                                    }}
                                >
                                    ✕
                                </button>
                            </div>
                        </div>
                        <div className="calendar-container">
                            <Calendar
                                localizer={localizer}
                                events={calendarEvents}
                                startAccessor="start"
                                endAccessor="end"
                                style={{ height: '100%' }}
                                views={isMobile ? ['day', 'agenda'] : ['week', 'day', 'agenda']}
                                view={currentView}
                                onView={setCurrentView}
                                date={currentDate}
                                onNavigate={(date) => setCurrentDate(date)}
                                min={new Date(1970, 1, 1, 8, 0, 0)}
                                eventPropGetter={eventStyleGetter}
                            />
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

export default App;
