const API_BASE_URL = '/api';

class API {
    static getToken() {
        let t = localStorage.getItem('access_token');
        if (!t || t === 'null' || t === 'undefined') {
            const cookieMatch = document.cookie.split('; ').find(row => row.startsWith('access_token='));
            if (cookieMatch) {
                t = cookieMatch.split('=')[1];
                if (t && t !== 'null' && t !== 'undefined') {
                    localStorage.setItem('access_token', t);
                }
            }
        }
        return (t && t !== 'null' && t !== 'undefined') ? t : null;
    }

    static setToken(token) {
        localStorage.setItem('access_token', token);
    }

    static clearToken() {
        localStorage.removeItem('access_token');
    }

    static isLoggedIn() {
        return !!this.getToken();
    }

    static async request(endpoint, options = {}) {
        const url = `${API_BASE_URL}${endpoint}`;
        
        const headers = {
            'Content-Type': 'application/json',
            ...options.headers
        };

        if (this.isLoggedIn()) {
            headers['Authorization'] = `Bearer ${this.getToken()}`;
        }

        if (options.body instanceof FormData) {
            delete headers['Content-Type'];
        }

        const config = {
            ...options,
            headers
        };

        try {
            const response = await fetch(url, config);
            const data = await response.json();
            
            if (!response.ok) {
                let errorMsg = 'An error occurred';
                if (data.detail) {
                    if (Array.isArray(data.detail)) {
                        errorMsg = data.detail.map(e => `${e.loc[e.loc.length-1]}: ${e.msg}`).join(', ');
                    } else {
                        errorMsg = data.detail;
                    }
                }
                throw new Error(errorMsg);
            }
            return data;
        } catch (error) {
            throw error;
        }
    }

    static async login(username, password) {
        const formData = new FormData();
        formData.append('username', username);
        formData.append('password', password);

        const data = await this.request('/auth/login', {
            method: 'POST',
            body: formData
        });
        
        this.setToken(data.access_token);
        return data;
    }

    static async register(username, email, password) {
        return this.request('/auth/register', {
            method: 'POST',
            body: JSON.stringify({ full_name: username, email: email, password: password })
        });
    }

    static async getProfile() {
        return this.request('/auth/me', { method: 'GET' });
    }

    static async getCourses() {
        return this.request('/courses/', { method: 'GET' });
    }

    static async getMyCourses() {
        return this.request('/subscriptions/my-courses', { method: 'GET' });
    }

    static async enrollCourse(courseId) {
        return this.request('/subscriptions/enroll', {
            method: 'POST',
            body: JSON.stringify({ course_id: courseId })
        });
    }

    static async getCourseDetails(courseId) {
        return this.request(`/courses/${courseId}`, { method: 'GET' });
    }

    static async askTutor(message, lessonId = null, skill = null) {
        return this.request('/chat/ask', {
            method: 'POST',
            body: JSON.stringify({ 
                message: message,
                lesson_id: lessonId,
                skill: skill
            })
        });
    }

    static async generateAICourse(skill, forceRegenerate = false) {
        return this.request('/courses/ai-course/generate', {
            method: 'POST',
            body: JSON.stringify({ 
                skill: skill,
                force_regenerate: forceRegenerate
            })
        });
    }

    static async getPlans() {
        return this.request('/subscriptions/plans', { method: 'GET' });
    }

    static async validateCoupon(couponCode, planName = 'Pro Monthly', amount = 19.99) {
        return this.request('/subscriptions/coupons/validate', {
            method: 'POST',
            body: JSON.stringify({
                code: couponCode,
                plan_name: planName,
                amount: amount
            })
        });
    }

    static async demoPayment(planName = 'Pro Monthly', couponCode = null, paymentMethod = 'demo_card', amountPaid = 19.99) {
        return this.request('/subscriptions/demo-payment', {
            method: 'POST',
            body: JSON.stringify({
                plan_name: planName,
                coupon_code: couponCode,
                payment_method: paymentMethod,
                amount_paid: amountPaid
            })
        });
    }

    static async createCourse(courseData) {
        const token = this.getToken();
        const headers = { 'Content-Type': 'application/json' };
        if (token) headers['Authorization'] = `Bearer ${token}`;
        const res = await fetch('/admin/create_course', {
            method: 'POST',
            headers: headers,
            body: JSON.stringify(courseData)
        });
        return await res.json();
    }

    static async getCourseModules(courseId) {
        return this.request(`/courses/${courseId}/modules`, { method: 'GET' });
    }

    static async createModule(courseId, moduleData) {
        return this.request(`/courses/${courseId}/modules`, {
            method: 'POST',
            body: JSON.stringify(moduleData)
        });
    }

    static async createLesson(lessonData) {
        return this.request('/admin/lessons/', {
            method: 'POST',
            body: JSON.stringify(lessonData)
        });
    }

    static async uploadVideo(lessonId, file) {
        const formData = new FormData();
        formData.append('video', file);
        return this.request(`/admin/lessons/${lessonId}/upload-video`, {
            method: 'POST',
            body: formData
        });
    }

    static async uploadNotes(lessonId, file) {
        const formData = new FormData();
        formData.append('notes', file);
        return this.request(`/admin/lessons/${lessonId}/upload-notes`, {
            method: 'POST',
            body: formData
        });
    }
}
