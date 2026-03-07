import React from 'react'
import Link from 'next/link'

const Workflow = () => {
    return (
        <div>
            <Link href="/">
                <button style={{ padding: '10px 20px', cursor: 'pointer' }} className='bg-red-600'>
                    Home page
                </button>
            </Link>
            <Link href="/dashboard">
                <button style={{ padding: '10px 20px', cursor: 'pointer' }} className='bg-red-600'>
                    Dashboard page
                </button>
            </Link>
        </div>
    )
}

export default Workflow