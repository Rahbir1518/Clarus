import React from 'react'
import Link from 'next/link'

const SignIn = () => {
    return (
        <div>
            <Link href="/dashboard">
                <button style={{ padding: '10px 20px', cursor: 'pointer' }} className='bg-red-600'>
                    go to Dashboard from Sign In
                </button>
            </Link>
        </div>
    )
}

export default SignIn