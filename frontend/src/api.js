// frontend/src/api.js
const API_BASE_URL = process.env.REACT_APP_API_BASE_URL || '';

export const searchCourses = async (filters) => {
    // Only include non-empty filter values
    const cleanFilters = Object.entries(filters).reduce((acc, [key, value]) => {
        if (value && value.trim() !== '') {
            acc[key] = value;
        }
        return acc;
    }, {});
    
    const params = new URLSearchParams(cleanFilters);
    const response = await fetch(`${API_BASE_URL}/search?${params.toString()}`);
    if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`HTTP error! status: ${response.status} - ${errorText}`);
    }
    return await response.json();
};

export const updateDatabase = async (force = false) => {
    const url = force 
        ? `${API_BASE_URL}/update-database?force=true`
        : `${API_BASE_URL}/update-database`;
    
    const response = await fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        }
    });
    if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`HTTP error! status: ${response.status} - ${errorText}`);
    }
    return await response.json();
};

export const getDatabaseStatus = async () => {
    const response = await fetch(`${API_BASE_URL}/database-status`);
    if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`HTTP error! status: ${response.status} - ${errorText}`);
    }
    return await response.json();
};

export const getCourseDetails = async (group, key, srcdb, matched) => {
    const response = await fetch(`${API_BASE_URL}/course-details`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            group,
            key,
            srcdb,
            matched
        })
    });
    if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`HTTP error! status: ${response.status} - ${errorText}`);
    }
    return await response.json();
};
