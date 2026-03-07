import React from 'react'
import Link from 'next/link'

const Dashboard = () => {
    return (
        <div>
            <Link href="/workflow">
                <button style={{ padding: '10px 20px', cursor: 'pointer' }} className='bg-red-600'>
                    Workflow page
                </button>
            </Link>
        </div>
    )
}

export default Dashboard