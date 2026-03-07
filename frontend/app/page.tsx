import Image from "next/image";
import Link from 'next/link'

const Workflow = () => {
  return (
    <div>
      <Link href="/signIn">
        <button style={{ padding: '10px 20px', cursor: 'pointer' }} className='bg-red-600'>
          SignIn page
        </button>
      </Link>
      <Link href="/signUp">
        <button style={{ padding: '10px 20px', cursor: 'pointer' }} className='bg-blue-600'>
          SignUp page
        </button>
      </Link>
    </div>
  )
}

export default Workflow