export interface Patient {
  id: string;
  firstName: string;
  lastName: string;
  phone: string;
  email?: string;
  optedOutOfCalls: boolean;
  doctorId: string;
  createdAt: string;
  updatedAt: string;
}
